"""Domain chokepoint for all document mutations and queries (ADR-0010 §6, module map §core/documents)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING, Literal

import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.core.document_access import (
    manageable_where,
    pending_invitation_disclosure_where,
    readable_where,
)
from buscasam.settings import settings

if TYPE_CHECKING:
    from buscasam.core.auth import UserCtx
    from buscasam.core.blob_store import BlobPutResult
    from buscasam.core.chunk import Chunk
    from buscasam.core.extract import IndexableMetadata


_EMBEDDING_MODEL_VERSION = "multilingual-e5-large@v1"


class _Unset:
    """Sentinel distinguishing an absent PATCH field from an explicit null."""


UNSET = _Unset()


def _halfvec_literal(values: np.ndarray) -> str:
    return "[" + ",".join(f"{float(v):.6f}" for v in values) + "]"


@dataclass(frozen=True)
class CandidateVersion:
    version_id: int
    doc_id: int
    sha256: str
    mime: str
    title: str
    owner_user_id: int | None


class DocumentNotFound(Exception):
    pass


class InvalidCoauthorId(Exception):
    def __init__(self, ids: set[int]) -> None:
        self.ids = ids


class PublishConflict(Exception):
    """The candidate is not indexed, or its stored headline fingerprint no
    longer matches current title + staged_abstract (→ 409)."""


class NoPublishedVersion(Exception):
    """replace_main_version on a document without a published current version
    (→ 409). The inverse of /upload's initial-publication-only entry state
    (module map §api/documents)."""


class AttachmentCapExceeded(Exception):
    """The document already holds the maximum of 5 attachments (→ 409)."""


class InvitationNotPending(Exception):
    """No `pending` row for `(doc_id, user_id)` on a readable document (→ 404):
    already-transitioned, revoked, never-invited, or the document
    soft-deleted / moderation-hidden / unpublished (PRD stories 20-22, 32-33)."""


class NotOwner(Exception):
    """Caller is not the document's owner (→ 403). Owner-only is stricter than
    manageable_where, which also admits accepted coautores (ADR-0010 §8)."""


class CoauthorAlreadyListed(Exception):
    """A document_authors row already exists for (doc_id, user_id), regardless
    of status (owner | pending | accepted | declined | external) (→ 409).
    Blocks re-invite of a declined user per ADR-0010 §5 / PRD story 10."""


class CoauthorNotPending(Exception):
    """Revoke is pending-only at MVP (ADR-0010 §5). Maps to 404 uniform with
    not-found — no leak about whether a non-pending row exists."""


@dataclass(frozen=True)
class AttachmentInfo:
    id: int
    original_filename: str
    size_bytes: int
    mime: str | None


CoauthorStatus = Literal["owner", "pending", "accepted", "declined", "external"]


@dataclass(frozen=True)
class CoauthorRow:
    user_id: int | None
    display_name: str
    email_local: str | None
    status: CoauthorStatus


@dataclass(frozen=True)
class CandidateState:
    """In-flight replacement candidate projection for the editar CandidatePanel
    (module map §core/documents, ADR-0011 §9). `status` is the raw lifecycle
    collapsed to the three UI states; the Spanish labels live on the frontend."""
    status: Literal["processing", "ready", "failed"]
    staged_abstract: str | None
    staged_keywords: list[str]
    staged_fecha: date | None
    can_publish: bool  # owner-only AND publish gate clear
    can_discard: bool  # manageable-scoped
    indexed_at: datetime | None
    error: str | None


def _candidate_status(index_status: str) -> Literal["processing", "ready", "failed"]:
    if index_status == "indexed":
        return "ready"
    if index_status == "failed":
        return "failed"
    return "processing"  # pending | processing


@dataclass(frozen=True)
class DraftState:
    doc_id: int
    version_id: int
    title: str
    index_status: str
    staged_abstract: str | None
    staged_keywords: list[str]
    staged_fecha: date | None
    index_error: str | None
    publish_gate_reason: str | None
    is_owner: bool
    attachments: list[AttachmentInfo]
    coauthors: list[CoauthorRow]
    versions: list[DetailVersion]
    candidate: CandidateState | None


def _publish_gate_reason(index_status: str, fingerprint_matches: bool) -> str | None:
    """Server-owned publish gate. None iff the candidate is indexed and its
    stored headline fingerprint matches current title + staged_abstract."""
    if index_status in ("pending", "processing"):
        return "processing"
    if index_status == "failed":
        return "processing_failed"
    if index_status == "indexed" and fingerprint_matches:
        return None
    return "reindexing_headline"


@dataclass(frozen=True)
class OwnDocSummary:
    id: int
    title: str
    publication_status: str
    visibility: str
    published_at: datetime | None


async def create_draft(
    session: AsyncSession,
    user_ctx: UserCtx,
    *,
    title: str,
    area_path: str,
    document_type: str,
    visibility: str,
    external_authors: list[str],
    coauthor_user_ids: list[int],
) -> int:
    owner_name = (
        await session.execute(
            text("SELECT name FROM users WHERE id = :uid"),
            {"uid": user_ctx.user_id},
        )
    ).scalar_one_or_none() or ""

    doc_id = (
        await session.execute(
            text(
                "INSERT INTO documents (visibility, publication_status, titulo, fecha, area_path, tipo) "
                "VALUES (:visibility, 'draft', :titulo, CURRENT_DATE, :area_path, :tipo) RETURNING id"
            ),
            {
                "visibility": visibility,
                "titulo": title,
                "area_path": area_path,
                "tipo": document_type,
            },
        )
    ).scalar_one()

    await session.execute(
        text(
            "INSERT INTO document_authors (doc_id, user_id, display_name, status) "
            "VALUES (:doc_id, :uid, :name, 'owner')"
        ),
        {"doc_id": doc_id, "uid": user_ctx.user_id, "name": owner_name},
    )

    coauthor_names: dict[int, str] = {}
    if coauthor_user_ids:
        rows = (
            await session.execute(
                text("SELECT id, name FROM users WHERE id = ANY(:ids)"),
                {"ids": coauthor_user_ids},
            )
        ).mappings().all()
        coauthor_names = {r["id"]: r["name"] for r in rows}
        missing = set(coauthor_user_ids) - coauthor_names.keys()
        if missing:
            raise InvalidCoauthorId(missing)

    for coauthor_id in coauthor_user_ids:
        await session.execute(
            text(
                "INSERT INTO document_authors (doc_id, user_id, display_name, status) "
                "VALUES (:doc_id, :uid, :name, 'pending')"
            ),
            {"doc_id": doc_id, "uid": coauthor_id, "name": coauthor_names[coauthor_id]},
        )

    for external_name in external_authors:
        await session.execute(
            text(
                "INSERT INTO document_authors (doc_id, user_id, display_name, status) "
                "VALUES (:doc_id, NULL, :name, 'external')"
            ),
            {"doc_id": doc_id, "name": external_name},
        )

    return doc_id


async def assert_manageable(
    session: AsyncSession,
    user_ctx: UserCtx,
    doc_id: int,
) -> None:
    where, params = manageable_where("d", user_ctx)
    exists = (
        await session.execute(
            text(f"SELECT 1 FROM documents d WHERE d.id = :doc_id AND ({where})"),
            {"doc_id": doc_id, **params},
        )
    ).scalar_one_or_none()
    if exists is None:
        raise DocumentNotFound


async def attach_main_version(
    session: AsyncSession,
    user_ctx: UserCtx,
    doc_id: int,
    blob: BlobPutResult,
    *,
    original_filename: str,
) -> int:
    await assert_manageable(session, user_ctx, doc_id)

    version_no = (
        await session.execute(
            text(
                "SELECT COALESCE(MAX(version_no), 0) + 1 "
                "FROM document_versions WHERE doc_id = :doc_id"
            ),
            {"doc_id": doc_id},
        )
    ).scalar_one()

    version_id = (
        await session.execute(
            text(
                "INSERT INTO document_versions "
                "(doc_id, version_no, sha256, original_filename, bytes, mime, uploaded_by) "
                "VALUES (:doc_id, :version_no, decode(:sha256, 'hex'), "
                ":filename, :bytes, :mime, :uid) RETURNING id"
            ),
            {
                "doc_id": doc_id,
                "version_no": version_no,
                "sha256": blob.sha256,
                "filename": original_filename,
                "bytes": blob.bytes,
                "mime": blob.sniffed_mime,
                "uid": user_ctx.user_id,
            },
        )
    ).scalar_one()

    # ADR-0008 §1: defer index_document through the active transaction so the
    # version row + the job row commit together.
    from buscasam.core import jobs

    await jobs.enqueue_index_document(session, version_id)

    return version_id


async def replace_main_version(
    session: AsyncSession,
    user_ctx: UserCtx,
    doc_id: int,
    blob: BlobPutResult,
    *,
    original_filename: str,
) -> int:
    """Insert a replacement candidate on an already-published document (module
    map §core/documents). Manageable-scoped; cross-user → DocumentNotFound.
    Raises NoPublishedVersion when no current published version exists. Discards
    any pre-existing non-discarded candidate inline so the partial unique index
    `document_versions_one_candidate` admits the new row, then inserts it
    (is_current=false, index_status='pending', first_published_at=NULL) with
    staged_* pre-filled from documents.* and enqueues index_document in the same
    transaction."""
    where, params = manageable_where("d", user_ctx)
    # FOR UPDATE OF d serializes concurrent replaces so the inline-discard +
    # insert pair cannot race a second uploader against the partial unique index.
    locked = (
        await session.execute(
            text(
                f"SELECT 1 FROM documents d WHERE d.id = :doc_id AND ({where}) "
                "FOR UPDATE OF d"
            ),
            {"doc_id": doc_id, **params},
        )
    ).scalar_one_or_none()
    if locked is None:
        raise DocumentNotFound

    has_current = (
        await session.execute(
            text(
                "SELECT 1 FROM document_versions "
                "WHERE doc_id = :doc_id AND is_current = true"
            ),
            {"doc_id": doc_id},
        )
    ).scalar_one_or_none()
    if has_current is None:
        raise NoPublishedVersion

    # ADR-0011 §2: at most one non-discarded, never-public candidate per doc.
    # Flip any pre-existing one to 'discarded' so the new insert is admitted.
    await session.execute(
        text(
            "UPDATE document_versions SET index_status = 'discarded' "
            "WHERE doc_id = :doc_id AND is_current = false "
            "  AND index_status <> 'discarded' AND first_published_at IS NULL"
        ),
        {"doc_id": doc_id},
    )

    version_no = (
        await session.execute(
            text(
                "SELECT COALESCE(MAX(version_no), 0) + 1 "
                "FROM document_versions WHERE doc_id = :doc_id"
            ),
            {"doc_id": doc_id},
        )
    ).scalar_one()

    version_id = (
        await session.execute(
            text(
                "INSERT INTO document_versions "
                "(doc_id, version_no, sha256, original_filename, bytes, mime, "
                " uploaded_by, index_status, is_current, "
                " staged_abstract, staged_keywords, staged_fecha) "
                "SELECT :doc_id, :version_no, decode(:sha256, 'hex'), :filename, "
                "       :bytes, :mime, :uid, 'pending', false, "
                "       d.abstract, d.keywords, d.fecha "
                "FROM documents d WHERE d.id = :doc_id RETURNING id"
            ),
            {
                "doc_id": doc_id,
                "version_no": version_no,
                "sha256": blob.sha256,
                "filename": original_filename,
                "bytes": blob.bytes,
                "mime": blob.sniffed_mime,
                "uid": user_ctx.user_id,
            },
        )
    ).scalar_one()

    # ADR-0008 §1: enqueue through the active transaction so the version row +
    # the job row commit together.
    from buscasam.core import jobs

    await jobs.enqueue_index_document(session, version_id)

    return version_id


async def load_candidate(
    session: AsyncSession, version_id: int
) -> CandidateVersion:
    row = (
        await session.execute(
            text(
                "SELECT v.id, v.doc_id, encode(v.sha256, 'hex') AS sha, v.mime, "
                "       d.titulo, "
                "       (SELECT a.user_id FROM document_authors a "
                "         WHERE a.doc_id = v.doc_id AND a.status = 'owner' LIMIT 1) "
                "         AS owner_user_id "
                "FROM document_versions v JOIN documents d ON d.id = v.doc_id "
                "WHERE v.id = :id"
            ),
            {"id": version_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise DocumentNotFound
    return CandidateVersion(
        version_id=row["id"],
        doc_id=row["doc_id"],
        sha256=row["sha"],
        mime=row["mime"],
        title=row["titulo"],
        owner_user_id=row["owner_user_id"],
    )


async def _begin_indexing(
    session: AsyncSession, version_id: int
) -> CandidateVersion | None:
    status = (
        await session.execute(
            text(
                "SELECT index_status FROM document_versions "
                "WHERE id = :id FOR UPDATE"
            ),
            {"id": version_id},
        )
    ).scalar_one_or_none()
    if status is None:
        raise DocumentNotFound
    if status == "indexed":
        return None
    await session.execute(
        text("UPDATE document_versions SET index_status = 'processing' WHERE id = :id"),
        {"id": version_id},
    )
    return await load_candidate(session, version_id)


async def write_indexed_candidate(
    session: AsyncSession,
    version_id: int,
    *,
    body: list["Chunk"],
    headline: "Chunk",
    embeds: list[np.ndarray],
    meta: "IndexableMetadata",
    headline_fingerprint: str,
) -> None:
    doc_id = (
        await session.execute(
            text("SELECT doc_id FROM document_versions WHERE id = :id"),
            {"id": version_id},
        )
    ).scalar_one()

    all_chunks = [headline, *body]
    for c, emb in zip(all_chunks, embeds):
        await session.execute(
            text(
                "INSERT INTO chunks (doc_id, chunk_seq, is_headline, body_text, "
                "  embedding, embedding_model_version, version_id, is_current) "
                "VALUES (:doc_id, :seq, :hl, :body, "
                "        cast(:emb as halfvec(1024)), :mv, :vid, false)"
            ),
            {
                "doc_id": doc_id,
                "seq": c.chunk_seq,
                "hl": c.is_headline,
                "body": c.body_text,
                "emb": _halfvec_literal(emb),
                "mv": _EMBEDDING_MODEL_VERSION,
                "vid": version_id,
            },
        )

    # Extraction is an initial fill, not an overwrite: a user who lands on the
    # editar form while still `processing` can save their own staged_* via
    # save-on-blur. COALESCE leaves any column they already wrote untouched
    # (staged_* are NULL until first written), so the author edit always wins.
    await session.execute(
        text(
            "UPDATE document_versions SET "
            "  index_status = 'indexed', "
            "  staged_abstract = COALESCE(staged_abstract, :abstract), "
            "  staged_keywords = COALESCE(staged_keywords, :keywords), "
            "  staged_fecha = COALESCE(staged_fecha, :fecha), "
            "  headline_fingerprint = :fp, "
            "  extract_pipeline_version = :pv, "
            "  indexed_at = now() "
            "WHERE id = :id"
        ),
        {
            "abstract": meta.abstract,
            "keywords": meta.keywords,
            "fecha": meta.fecha,
            "fp": headline_fingerprint,
            "pv": settings.extract_pipeline_version,
            "id": version_id,
        },
    )

    # A título/abstract edit can land after this task embedded its headline (the
    # index window spans minutes for OCR). The R001 guard suppresses the enqueue
    # while processing, so the stamped fingerprint is now stale against the
    # current título + preserved staged_abstract with no refresh queued — a
    # permanently stuck `reindexing_headline` gate. Detect the drift here and
    # enqueue the refresh ourselves so the headline catches up to the edit.
    from buscasam.core.chunk import headline_fingerprint as _compute_fp

    drift = (
        await session.execute(
            text(
                "SELECT d.titulo, v.staged_abstract "
                "FROM document_versions v JOIN documents d ON d.id = v.doc_id "
                "WHERE v.id = :id"
            ),
            {"id": version_id},
        )
    ).mappings().one()
    if _compute_fp(drift["titulo"], drift["staged_abstract"] or "") != headline_fingerprint:
        from buscasam.core import jobs

        await jobs.enqueue_refresh_headline(session, version_id)


async def write_headline(
    session: AsyncSession,
    version_id: int,
    headline: "Chunk",
    embed: np.ndarray,
    headline_fingerprint: str,
) -> None:
    """ADR-0007 §10: only write if the row's title+abstract still match the
    fingerprint the caller computed for this embedding. A racing edit that
    updates staged_abstract between embed-time and write-time wins."""
    from buscasam.core.chunk import headline_fingerprint as _compute_fp

    row = (
        await session.execute(
            text(
                "SELECT v.doc_id, v.is_current, d.titulo, v.staged_abstract "
                "FROM document_versions v JOIN documents d ON d.id = v.doc_id "
                "WHERE v.id = :id FOR UPDATE OF v"
            ),
            {"id": version_id},
        )
    ).mappings().one_or_none()
    if row is None:
        return
    current_fp = _compute_fp(row["titulo"], row["staged_abstract"] or "")
    if current_fp != headline_fingerprint:
        # Title or abstract changed since this task computed its embedding;
        # let the newer refresh_headline task own the write.
        return
    doc_id = row["doc_id"]

    await session.execute(
        text(
            "DELETE FROM chunks WHERE version_id = :vid AND is_headline"
        ),
        {"vid": version_id},
    )
    await session.execute(
        text(
            "INSERT INTO chunks (doc_id, chunk_seq, is_headline, body_text, "
            "  embedding, embedding_model_version, version_id, is_current) "
            "VALUES (:doc_id, 0, true, :body, "
            "        cast(:emb as halfvec(1024)), :mv, :vid, :is_current)"
        ),
        {
            "doc_id": doc_id,
            "body": headline.body_text,
            "emb": _halfvec_literal(embed),
            "mv": _EMBEDDING_MODEL_VERSION,
            "vid": version_id,
            "is_current": row["is_current"],
        },
    )
    await session.execute(
        text(
            "UPDATE document_versions SET headline_fingerprint = :fp WHERE id = :id"
        ),
        {"fp": headline_fingerprint, "id": version_id},
    )


async def mark_failed(
    session: AsyncSession, version_id: int, error: str
) -> None:
    """Candidate terminal-state writer (ADR-0008 §5, ADR-0010 §9).

    Single seam called by every fatal indexing path — recognized parse/OCR
    failures and exhausted transient failures (`core/jobs._run_attempt`). The
    UPDATE is first-write-wins so a later `exhausted retries:` reason cannot
    overwrite an earlier, more specific `corrupted:` cause. The notification
    insert is deduped at the unique (user_id, event_key) index.
    """
    cv = await load_candidate(session, version_id)
    await session.execute(
        text(
            "UPDATE document_versions SET index_status = 'failed', "
            "  index_error = :err "
            "WHERE id = :id AND index_status <> 'failed'"
        ),
        {"err": error, "id": version_id},
    )
    if cv.owner_user_id is None:
        return
    await session.execute(
        text(
            "INSERT INTO notifications (user_id, event_key, kind, payload_json) "
            "VALUES (:uid, :ek, 'processing_failed', "
            "        jsonb_build_object('doc_id', cast(:doc_id as bigint), "
            "                           'version_id', cast(:vid as bigint), "
            "                           'error', cast(:err as text))) "
            "ON CONFLICT (user_id, event_key) DO NOTHING"
        ),
        {
            "uid": cv.owner_user_id,
            "ek": f"processing_failed:{version_id}",
            "doc_id": cv.doc_id,
            "vid": version_id,
            "err": error,
        },
    )


async def mark_headline_refresh_failed(
    session: AsyncSession, version_id: int, *, reason: str
) -> None:
    """ADR-0008 §5 row 3: refresh_headline exhausted retries.

    Leaves `index_status` alone (published headline stays current; draft
    publish stays blocked by the fingerprint mismatch) and inserts a deduped
    notification keyed on `headline_refresh_failed:{vid}`. Same `kind` as
    indexing failures so the consumer list does not need a new branch.
    """
    cv = await load_candidate(session, version_id)
    if cv.owner_user_id is None:
        return
    await session.execute(
        text(
            "INSERT INTO notifications (user_id, event_key, kind, payload_json) "
            "VALUES (:uid, :ek, 'processing_failed', "
            "        jsonb_build_object('doc_id', cast(:doc_id as bigint), "
            "                           'version_id', cast(:vid as bigint), "
            "                           'error', cast(:err as text))) "
            "ON CONFLICT (user_id, event_key) DO NOTHING"
        ),
        {
            "uid": cv.owner_user_id,
            "ek": f"headline_refresh_failed:{version_id}",
            "doc_id": cv.doc_id,
            "vid": version_id,
            "err": reason,
        },
    )


async def update_draft_metadata(
    session: AsyncSession,
    user_ctx: UserCtx,
    doc_id: int,
    *,
    title: str | None = None,
    abstract: str | None = None,
    keywords: list[str] | None = None,
    fecha: date | None | _Unset = UNSET,
    visibility: str | None = None,
    area_path: str | None = None,
    document_type: str | None = None,
) -> None:
    """Writes top-level fields to `documents`, staged_* to the candidate version,
    and enqueues refresh_headline when title or abstract changed (module map
    §core/documents). Manageable-scoped; cross-user → DocumentNotFound."""
    await assert_manageable(session, user_ctx, doc_id)

    # Pre-update candidate state: drives change-detection and the index_status
    # guard on the headline reindex enqueue below.
    current = (
        await session.execute(
            text(
                "SELECT v.id AS version_id, v.index_status, v.staged_abstract, "
                "       d.titulo "
                "FROM document_versions v JOIN documents d ON d.id = v.doc_id "
                "WHERE v.doc_id = :doc_id ORDER BY v.version_no DESC LIMIT 1"
            ),
            {"doc_id": doc_id},
        )
    ).mappings().one_or_none()

    doc_sets: list[str] = []
    doc_params: dict = {"doc_id": doc_id}
    if title is not None:
        doc_sets.append("titulo = :titulo")
        doc_params["titulo"] = title
    if visibility is not None:
        doc_sets.append("visibility = :visibility")
        doc_params["visibility"] = visibility
    if area_path is not None:
        doc_sets.append("area_path = :area_path")
        doc_params["area_path"] = area_path
    if document_type is not None:
        doc_sets.append("tipo = :tipo")
        doc_params["tipo"] = document_type
    if doc_sets:
        await session.execute(
            text(f"UPDATE documents SET {', '.join(doc_sets)} WHERE id = :doc_id"),
            doc_params,
        )

    if current is None:
        return
    version_id = current["version_id"]

    ver_sets: list[str] = []
    ver_params: dict = {"vid": version_id}
    if abstract is not None:
        ver_sets.append("staged_abstract = :abstract")
        ver_params["abstract"] = abstract
    if keywords is not None:
        ver_sets.append("staged_keywords = :keywords")
        ver_params["keywords"] = keywords
    if not isinstance(fecha, _Unset):
        ver_sets.append("staged_fecha = :fecha")
        ver_params["fecha"] = fecha
    if ver_sets:
        await session.execute(
            text(
                f"UPDATE document_versions SET {', '.join(ver_sets)} WHERE id = :vid"
            ),
            ver_params,
        )

    # Reindex only when a headline input actually changed AND the candidate is
    # already indexed: while still processing, index_document builds the headline
    # from the current title, so a concurrent refresh would duplicate it.
    title_changed = title is not None and title != current["titulo"]
    abstract_changed = abstract is not None and abstract != (
        current["staged_abstract"] or ""
    )
    if current["index_status"] == "indexed" and (title_changed or abstract_changed):
        from buscasam.core import jobs

        await jobs.enqueue_refresh_headline(session, version_id)


async def publish(session: AsyncSession, user_ctx: UserCtx, doc_id: int) -> None:
    """Atomic staged → current flip (ADR-0006 §6). Owner-only: cross-user and
    non-owner coauthors raise DocumentNotFound. Raises PublishConflict if the
    candidate is not indexed or its stored headline_fingerprint no longer
    matches current title + staged_abstract (module map §core/documents)."""
    # FOR UPDATE OF v, d serializes against concurrent update_draft_metadata:
    # without it, a PATCH committing between this SELECT and the UPDATEs below
    # could change títuto/staged_abstract while we still copy the pre-edit
    # staged_abstract into documents.abstract — yielding a published row with
    # mismatched títuto/abstract and a stale headline_fingerprint.
    row = (
        await session.execute(
            text(
                "SELECT v.id AS version_id, v.index_status, v.staged_abstract, "
                "       v.staged_keywords, v.staged_fecha, v.headline_fingerprint, "
                "       d.titulo, "
                "       (SELECT a.user_id FROM document_authors a "
                "         WHERE a.doc_id = d.id AND a.status = 'owner' LIMIT 1) "
                "         AS owner_user_id "
                "FROM document_versions v JOIN documents d ON d.id = v.doc_id "
                "WHERE v.doc_id = :doc_id ORDER BY v.version_no DESC LIMIT 1 "
                "FOR UPDATE OF v, d"
            ),
            {"doc_id": doc_id},
        )
    ).mappings().one_or_none()
    if row is None or row["owner_user_id"] != user_ctx.user_id:
        raise DocumentNotFound

    from buscasam.core.chunk import headline_fingerprint

    matches = row["headline_fingerprint"] == headline_fingerprint(
        row["titulo"], row["staged_abstract"] or ""
    )
    if row["index_status"] != "indexed" or not matches:
        raise PublishConflict

    version_id = row["version_id"]
    # ADR-0006 §6: flip the previously-current version + its chunks off, the
    # candidate on. First publish has no prior current version (no-op flip).
    await session.execute(
        text("UPDATE chunks SET is_current = false WHERE doc_id = :doc_id AND is_current"),
        {"doc_id": doc_id},
    )
    await session.execute(
        text(
            "UPDATE document_versions SET is_current = false "
            "WHERE doc_id = :doc_id AND is_current"
        ),
        {"doc_id": doc_id},
    )
    await session.execute(
        text("UPDATE chunks SET is_current = true WHERE version_id = :v"),
        {"v": version_id},
    )
    # ADR-0011 §3: stamp first_published_at on the candidate the first time it
    # is promoted. Immutable once set; a republish does not re-stamp. Stamping
    # here also lifts the row out of `document_versions_one_candidate` so the
    # next replacement's candidate insert is admitted.
    await session.execute(
        text(
            "UPDATE document_versions SET is_current = true, "
            "  first_published_at = COALESCE(first_published_at, now()) "
            "WHERE id = :v"
        ),
        {"v": version_id},
    )
    await session.execute(
        text(
            "UPDATE documents SET publication_status = 'published', "
            "  published_at = now(), abstract = :abs, keywords = :kw, "
            "  fecha = COALESCE(:fec, fecha) WHERE id = :doc_id"
        ),
        {
            "abs": row["staged_abstract"],
            "kw": row["staged_keywords"],
            "fec": row["staged_fecha"],
            "doc_id": doc_id,
        },
    )

    # Fan out in-app invites for any pending coautores, transactional with the
    # publish flip (ADR-0008 §1, module map §core/jobs).
    from buscasam.core import jobs

    await jobs.enqueue_fan_out_coauthor_invites(session, doc_id)


async def _assert_owner(
    session: AsyncSession, user_ctx: UserCtx, doc_id: int
) -> None:
    """Owner-only predicate stricter than manageable_where: accepted coautores
    cannot manage coauthors (ADR-0010 §8, module map §core/documents)."""
    is_owner = (
        await session.execute(
            text(
                "SELECT 1 FROM document_authors "
                "WHERE doc_id = :doc_id AND user_id = :uid AND status = 'owner'"
            ),
            {"doc_id": doc_id, "uid": user_ctx.user_id},
        )
    ).scalar_one_or_none()
    if is_owner is None:
        raise NotOwner


async def invite_coauthor(
    session: AsyncSession,
    user_ctx: UserCtx,
    doc_id: int,
    invitee_user_id: int,
) -> None:
    """Owner-only invite. Inserts a pending document_authors row; raises
    CoauthorAlreadyListed if any row exists for (doc_id, user_id) regardless
    of status (PRD story 10). On a published doc, enqueues the fan-out task
    in the same transaction (ADR-0008 §1) so the invitee notification appears
    immediately. On a draft, the row sits silent until publish picks it up."""
    await _assert_owner(session, user_ctx, doc_id)

    name = (
        await session.execute(
            text("SELECT name FROM users WHERE id = :uid"),
            {"uid": invitee_user_id},
        )
    ).scalar_one_or_none()
    if name is None:
        raise InvalidCoauthorId({invitee_user_id})

    # ON CONFLICT against the partial unique index is the race-safe gate: a
    # concurrent invite for the same (doc, user) loses here and we raise the
    # documented 409 instead of an IntegrityError-as-500.
    inserted = (
        await session.execute(
            text(
                "INSERT INTO document_authors (doc_id, user_id, display_name, status) "
                "VALUES (:doc_id, :uid, :name, 'pending') "
                "ON CONFLICT (doc_id, user_id) WHERE user_id IS NOT NULL DO NOTHING "
                "RETURNING id"
            ),
            {"doc_id": doc_id, "uid": invitee_user_id, "name": name},
        )
    ).scalar_one_or_none()
    if inserted is None:
        raise CoauthorAlreadyListed

    publication_status = (
        await session.execute(
            text("SELECT publication_status FROM documents WHERE id = :doc_id"),
            {"doc_id": doc_id},
        )
    ).scalar_one()
    if publication_status == "published":
        from buscasam.core import jobs

        await jobs.enqueue_fan_out_coauthor_invites(session, doc_id)


async def revoke_invitation(
    session: AsyncSession,
    user_ctx: UserCtx,
    doc_id: int,
    invitee_user_id: int,
) -> None:
    """Owner-only, pending-only at MVP (ADR-0010 §5). Atomic DELETE of the
    document_authors row + DELETE of the matching notifications row so a later
    re-invite under the same dedup key can INSERT cleanly without an UPSERT
    (PRD story 29, module map §core/documents)."""
    await _assert_owner(session, user_ctx, doc_id)

    result = await session.execute(
        text(
            "DELETE FROM document_authors "
            "WHERE doc_id = :doc_id AND user_id = :uid AND status = 'pending'"
        ),
        {"doc_id": doc_id, "uid": invitee_user_id},
    )
    if result.rowcount == 0:
        raise CoauthorNotPending

    from buscasam.core.jobs import coauthor_invite_event_key

    await session.execute(
        text(
            "DELETE FROM notifications "
            "WHERE user_id = :uid AND event_key = :ek"
        ),
        {
            "uid": invitee_user_id,
            "ek": coauthor_invite_event_key(doc_id, invitee_user_id),
        },
    )


async def accept_invitation(
    session: AsyncSession, user_ctx: UserCtx, doc_id: int
) -> None:
    """Invitee flips their own pending row to accepted and marks the matching
    invite notification read, atomically (module map §core/documents). Raises
    InvitationNotPending for any miss — already-transitioned, revoked,
    never-invited, or the document soft-deleted / moderation-hidden /
    unpublished — which the router maps to a uniform 404 (PRD stories 20-22,
    32-33)."""
    await _transition_invitation(session, user_ctx, doc_id, "accepted")


async def decline_invitation(
    session: AsyncSession, user_ctx: UserCtx, doc_id: int
) -> None:
    """Sticky terminal decline; same atomicity and miss semantics as
    accept_invitation (ADR-0010 §5)."""
    await _transition_invitation(session, user_ctx, doc_id, "declined")


async def _transition_invitation(
    session: AsyncSession,
    user_ctx: UserCtx,
    doc_id: int,
    new_status: Literal["accepted", "declined"],
) -> None:
    # Idempotency lives at the row level: the status='pending' predicate stops
    # matching after the first transition, so a re-submit is a 0-row UPDATE. The
    # readable-lifecycle guards mean a hidden/soft-deleted doc cannot ratify.
    flipped = await session.execute(
        text(
            "UPDATE document_authors SET status = :new_status "
            "WHERE doc_id = :doc_id AND user_id = :uid AND status = 'pending' "
            "  AND EXISTS (SELECT 1 FROM documents d WHERE d.id = :doc_id "
            "              AND d.publication_status = 'published' "
            "              AND d.soft_deleted_at IS NULL "
            "              AND d.moderation_hidden_at IS NULL)"
        ),
        {"new_status": new_status, "doc_id": doc_id, "uid": user_ctx.user_id},
    )
    if flipped.rowcount == 0:
        raise InvitationNotPending

    from buscasam.core.jobs import coauthor_invite_event_key

    await session.execute(
        text(
            "UPDATE notifications SET read_at = now() "
            "WHERE user_id = :uid AND event_key = :ek"
        ),
        {
            "uid": user_ctx.user_id,
            "ek": coauthor_invite_event_key(doc_id, user_ctx.user_id),
        },
    )


async def add_attachment(
    session: AsyncSession,
    user_ctx: UserCtx,
    doc_id: int,
    blob: BlobPutResult,
    *,
    original_filename: str,
) -> int:
    where, params = manageable_where("d", user_ctx)
    # FOR UPDATE OF d serializes concurrent attachment inserts for this document
    # so the 5-cap below cannot be raced (ADR-0006 §7): a second uploader blocks
    # here until the first commits, then re-counts against the committed rows.
    locked = (
        await session.execute(
            text(
                f"SELECT 1 FROM documents d WHERE d.id = :doc_id AND ({where}) "
                "FOR UPDATE OF d"
            ),
            {"doc_id": doc_id, **params},
        )
    ).scalar_one_or_none()
    if locked is None:
        raise DocumentNotFound

    count = (
        await session.execute(
            text("SELECT count(*) FROM document_attachments WHERE doc_id = :doc_id"),
            {"doc_id": doc_id},
        )
    ).scalar_one()
    if count >= 5:
        raise AttachmentCapExceeded

    return (
        await session.execute(
            text(
                "INSERT INTO document_attachments "
                "(doc_id, sha256, original_filename, bytes, mime, uploaded_by) "
                "VALUES (:doc_id, decode(:sha, 'hex'), :fn, :bytes, :mime, :uid) "
                "RETURNING id"
            ),
            {
                "doc_id": doc_id,
                "sha": blob.sha256,
                "fn": original_filename,
                "bytes": blob.bytes,
                "mime": blob.sniffed_mime,
                "uid": user_ctx.user_id,
            },
        )
    ).scalar_one()


async def remove_attachment(
    session: AsyncSession, user_ctx: UserCtx, doc_id: int, att_id: int
) -> None:
    """Manageable-scoped delete of one attachment row. The underlying blob is
    left for the orphan sweep (dedup-safe). Cross-user docs and missing rows
    both raise DocumentNotFound (→ 404)."""
    await assert_manageable(session, user_ctx, doc_id)
    result = await session.execute(
        text(
            "DELETE FROM document_attachments "
            "WHERE id = :att_id AND doc_id = :doc_id"
        ),
        {"att_id": att_id, "doc_id": doc_id},
    )
    if result.rowcount == 0:
        raise DocumentNotFound


async def get_draft_state(
    session: AsyncSession, user_ctx: UserCtx, doc_id: int
) -> DraftState:
    await assert_manageable(session, user_ctx, doc_id)
    row = (
        await session.execute(
            text(
                "SELECT v.id AS version_id, v.index_status, v.staged_abstract, "
                "       v.staged_keywords, v.staged_fecha, v.index_error, "
                "       v.headline_fingerprint, d.titulo, "
                "       (SELECT a.user_id FROM document_authors a "
                "         WHERE a.doc_id = d.id AND a.status = 'owner' LIMIT 1) "
                "         AS owner_user_id "
                "FROM document_versions v JOIN documents d ON d.id = v.doc_id "
                "WHERE v.doc_id = :doc_id ORDER BY v.version_no DESC LIMIT 1"
            ),
            {"doc_id": doc_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise DocumentNotFound

    from buscasam.core.chunk import headline_fingerprint

    matches = row["headline_fingerprint"] == headline_fingerprint(
        row["titulo"], row["staged_abstract"] or ""
    )
    att_rows = (
        await session.execute(
            text(
                "SELECT id, original_filename, bytes, mime "
                "FROM document_attachments WHERE doc_id = :doc_id ORDER BY id"
            ),
            {"doc_id": doc_id},
        )
    ).mappings().all()
    # ADR-0011 §4: the editar Versiones list mirrors get_detail.versions —
    # only previously-public rows, by the same 1-based n ordering.
    version_rows = (
        await session.execute(
            text(
                "SELECT row_number() OVER (ORDER BY id) AS n, "
                "       original_filename, mime, bytes, indexed_at, is_current "
                "FROM document_versions "
                "WHERE doc_id = :doc_id AND first_published_at IS NOT NULL "
                "ORDER BY id"
            ),
            {"doc_id": doc_id},
        )
    ).mappings().all()
    # ADR-0011 §9: the in-flight replacement candidate, if any. The partial
    # unique index admits at most one (never-public, non-discarded, non-current)
    # row, so one_or_none is the contract, not a LIMIT.
    is_owner = row["owner_user_id"] == user_ctx.user_id
    cand_row = (
        await session.execute(
            text(
                "SELECT v.index_status, v.staged_abstract, v.staged_keywords, "
                "       v.staged_fecha, v.indexed_at, v.index_error, "
                "       v.headline_fingerprint, d.titulo "
                "FROM document_versions v JOIN documents d ON d.id = v.doc_id "
                "WHERE v.doc_id = :doc_id AND v.is_current = false "
                "  AND v.index_status <> 'discarded' "
                "  AND v.first_published_at IS NULL"
            ),
            {"doc_id": doc_id},
        )
    ).mappings().one_or_none()
    candidate: CandidateState | None = None
    if cand_row is not None:
        cand_matches = cand_row["headline_fingerprint"] == headline_fingerprint(
            cand_row["titulo"], cand_row["staged_abstract"] or ""
        )
        candidate = CandidateState(
            status=_candidate_status(cand_row["index_status"]),
            staged_abstract=cand_row["staged_abstract"],
            staged_keywords=cand_row["staged_keywords"] or [],
            staged_fecha=cand_row["staged_fecha"],
            can_publish=is_owner
            and _publish_gate_reason(cand_row["index_status"], cand_matches) is None,
            can_discard=True,
            indexed_at=cand_row["indexed_at"],
            error=cand_row["index_error"],
        )
    # Owner row first, then insertion order. The CASE keeps the owner pinned
    # regardless of the row id; document_authors.id is monotonic per insert so
    # ordering by id is the insertion order the module map prescribes.
    coauthor_rows = (
        await session.execute(
            text(
                "SELECT da.user_id, da.display_name, da.status, "
                "       split_part(u.email, '@', 1) AS email_local "
                "FROM document_authors da "
                "LEFT JOIN users u ON u.id = da.user_id "
                "WHERE da.doc_id = :doc_id "
                "ORDER BY (da.status = 'owner') DESC, da.id"
            ),
            {"doc_id": doc_id},
        )
    ).mappings().all()
    return DraftState(
        doc_id=doc_id,
        version_id=row["version_id"],
        title=row["titulo"],
        index_status=row["index_status"],
        staged_abstract=row["staged_abstract"],
        staged_keywords=row["staged_keywords"] or [],
        staged_fecha=row["staged_fecha"],
        index_error=row["index_error"],
        publish_gate_reason=_publish_gate_reason(
            row["index_status"], matches
        ),
        is_owner=is_owner,
        attachments=[
            AttachmentInfo(
                id=a["id"],
                original_filename=a["original_filename"],
                size_bytes=a["bytes"],
                mime=a["mime"],
            )
            for a in att_rows
        ],
        coauthors=[
            CoauthorRow(
                user_id=c["user_id"],
                display_name=c["display_name"],
                email_local=c["email_local"],
                status=c["status"],
            )
            for c in coauthor_rows
        ],
        versions=[
            DetailVersion(
                n=v["n"],
                original_filename=v["original_filename"],
                mime=v["mime"],
                size_bytes=v["bytes"],
                indexed_at=v["indexed_at"],
                is_current=v["is_current"],
            )
            for v in version_rows
        ],
        candidate=candidate,
    )


async def list_own_documents(
    session: AsyncSession, user_ctx: UserCtx
) -> list[OwnDocSummary]:
    where, params = manageable_where("d", user_ctx)
    rows = (
        await session.execute(
            text(
                f"SELECT d.id, d.titulo, d.publication_status, d.visibility, "
                f"       d.published_at "
                f"FROM documents d WHERE {where} ORDER BY d.id"
            ),
            params,
        )
    ).mappings().all()
    return [
        OwnDocSummary(
            id=r["id"],
            title=r["titulo"],
            publication_status=r["publication_status"],
            visibility=r["visibility"],
            published_at=r["published_at"],
        )
        for r in rows
    ]


@dataclass(frozen=True)
class AuthorDisplay:
    display_name: str
    user_id: int | None


@dataclass(frozen=True)
class MainFile:
    original_filename: str
    size_bytes: int
    mime: str


@dataclass(frozen=True)
class Attachment:
    id: int
    original_filename: str
    size_bytes: int
    mime: str | None


@dataclass(frozen=True)
class DetailVersion:
    n: int  # 1-based row_number ordering, shared with the version-download route
    original_filename: str
    mime: str
    size_bytes: int
    indexed_at: datetime | None
    is_current: bool


@dataclass(frozen=True)
class DetailRow:
    doc_id: int
    titulo: str
    autores: list[AuthorDisplay]
    area_path: str
    tipo: str
    fecha: date | None
    visibility: str
    abstract: str
    palabras_clave: list[str]
    archivo_principal: MainFile
    adjuntos: list[Attachment]
    versions: list[DetailVersion] | None
    manageable: bool


async def get_detail(
    session: AsyncSession,
    doc_id: int,
    user_ctx: UserCtx,
) -> DetailRow | None:
    """Reader DTO for `/docs/{id}` (module map §core/documents).

    Returns `None` when the document fails `readable_where(user_ctx)` — the
    router maps `None → 404` uniformly. `archivo_principal` and `adjuntos`
    reflect the published current version's rows (`document_versions.is_current`)
    and `document_attachments` respectively. `versions` (ascending by 1-based
    `n`) and `manageable=True` are populated only when `manageable_where(user_ctx)`
    admits the requester (owner / accepted coautor); for any other reader
    `versions is None` and `manageable=False` (issue #44).
    """
    where, params = readable_where("d", user_ctx)
    row = (
        await session.execute(
            text(
                "SELECT d.id, d.titulo, d.area_path::text AS area_path, d.tipo, "
                "       d.fecha, d.visibility, d.abstract, "
                "       COALESCE(d.keywords, ARRAY[]::text[]) AS keywords, "
                "       dv.original_filename AS main_filename, "
                "       dv.bytes AS main_bytes, "
                "       dv.mime AS main_mime "
                "FROM documents d "
                "JOIN document_versions dv "
                "  ON dv.doc_id = d.id AND dv.is_current "
                f"WHERE d.id = :doc_id AND ({where})"
            ),
            {"doc_id": doc_id, **params},
        )
    ).mappings().first()
    if row is None:
        return None

    author_rows = (
        await session.execute(
            text(
                "SELECT display_name, user_id "
                "FROM document_authors WHERE doc_id = :d ORDER BY id"
            ),
            {"d": doc_id},
        )
    ).mappings().all()
    attachment_rows = (
        await session.execute(
            text(
                "SELECT id, original_filename, bytes, mime "
                "FROM document_attachments WHERE doc_id = :d ORDER BY id"
            ),
            {"d": doc_id},
        )
    ).mappings().all()

    mgmt_where, mgmt_params = manageable_where("d", user_ctx)
    manageable = (
        await session.execute(
            text(f"SELECT 1 FROM documents d WHERE d.id = :doc_id AND ({mgmt_where})"),
            {"doc_id": doc_id, **mgmt_params},
        )
    ).scalar_one_or_none() is not None

    versions: list[DetailVersion] | None = None
    if manageable:
        # ADR-0011 §4: the audit list shows only versions that were at some
        # point the public current. The same first_published_at filter narrows
        # get_manageable_version_file, so the 1-based n stays aligned with the
        # version-download route.
        version_rows = (
            await session.execute(
                text(
                    "SELECT row_number() OVER (ORDER BY id) AS n, "
                    "       original_filename, mime, bytes, indexed_at, is_current "
                    "FROM document_versions "
                    "WHERE doc_id = :d AND first_published_at IS NOT NULL "
                    "ORDER BY id"
                ),
                {"d": doc_id},
            )
        ).mappings().all()
        versions = [
            DetailVersion(
                n=v["n"],
                original_filename=v["original_filename"],
                mime=v["mime"],
                size_bytes=v["bytes"],
                indexed_at=v["indexed_at"],
                is_current=v["is_current"],
            )
            for v in version_rows
        ]

    return DetailRow(
        doc_id=row["id"],
        titulo=row["titulo"],
        autores=[
            AuthorDisplay(display_name=a["display_name"], user_id=a["user_id"])
            for a in author_rows
        ],
        area_path=row["area_path"],
        tipo=row["tipo"],
        fecha=row["fecha"],
        visibility=row["visibility"],
        abstract=row["abstract"] or "",
        palabras_clave=list(row["keywords"]),
        archivo_principal=MainFile(
            original_filename=row["main_filename"],
            size_bytes=row["main_bytes"],
            mime=row["main_mime"],
        ),
        adjuntos=[
            Attachment(
                id=a["id"],
                original_filename=a["original_filename"],
                size_bytes=a["bytes"],
                mime=a["mime"],
            )
            for a in attachment_rows
        ],
        versions=versions,
        manageable=manageable,
    )


@dataclass(frozen=True)
class InvitationDisclosure:
    doc_id: int
    titulo: str
    inviter_display_name: str


async def get_pending_invitation(
    session: AsyncSession, doc_id: int, user_ctx: UserCtx
) -> InvitationDisclosure | None:
    """Minimal-block payload for a pending invitee on `doc_id`, else `None`.

    Composes `pending_invitation_disclosure_where` (ADR-0010 §6) — the sole
    reader of `document_authors.status='pending'` for disclosure. Returns `None`
    for guests (no `user_id`) without raising. `inviter_display_name` comes from
    the document's `owner` author row, consistent with `get_detail`'s autores.
    """
    if user_ctx.user_id is None:
        return None
    where, params = pending_invitation_disclosure_where("d", user_ctx)
    row = (
        await session.execute(
            text(
                "SELECT d.titulo, "
                "       (SELECT a.display_name FROM document_authors a "
                "         WHERE a.doc_id = d.id AND a.status = 'owner' LIMIT 1) "
                "         AS inviter "
                f"FROM documents d WHERE d.id = :doc_id AND ({where})"
            ),
            {"doc_id": doc_id, **params},
        )
    ).mappings().first()
    if row is None:
        return None
    return InvitationDisclosure(
        doc_id=doc_id,
        titulo=row["titulo"],
        inviter_display_name=row["inviter"],
    )


@dataclass(frozen=True)
class DownloadableFile:
    sha_hex: str
    original_filename: str
    mime: str | None  # NULL only possible for attachments (migration 0010)


async def get_readable_main_file(
    session: AsyncSession,
    doc_id: int,
    user_ctx: UserCtx,
) -> DownloadableFile | None:
    """Current published main-file lookup gated by `readable_where`.

    Returns `None` for missing doc, denied access, or no `is_current` version.
    Router maps `None → 404`.
    """
    where, params = readable_where("d", user_ctx)
    row = (
        await session.execute(
            text(
                "SELECT encode(dv.sha256, 'hex') AS sha, "
                "       dv.original_filename, dv.mime "
                "FROM documents d "
                "JOIN document_versions dv "
                "  ON dv.doc_id = d.id AND dv.is_current "
                f"WHERE d.id = :doc_id AND ({where})"
            ),
            {"doc_id": doc_id, **params},
        )
    ).first()
    if row is None:
        return None
    return DownloadableFile(
        sha_hex=row.sha, original_filename=row.original_filename, mime=row.mime
    )


async def get_readable_attachment(
    session: AsyncSession,
    doc_id: int,
    att_id: int,
    user_ctx: UserCtx,
) -> DownloadableFile | None:
    """Attachment lookup gated by `readable_where`. `mime` may be NULL."""
    where, params = readable_where("d", user_ctx)
    row = (
        await session.execute(
            text(
                "SELECT encode(a.sha256, 'hex') AS sha, "
                "       a.original_filename, a.mime "
                "FROM documents d "
                "JOIN document_attachments a "
                "  ON a.doc_id = d.id "
                f"WHERE d.id = :doc_id AND a.id = :att_id AND ({where})"
            ),
            {"doc_id": doc_id, "att_id": att_id, **params},
        )
    ).first()
    if row is None:
        return None
    return DownloadableFile(
        sha_hex=row.sha, original_filename=row.original_filename, mime=row.mime
    )


async def get_manageable_version_file(
    session: AsyncSession,
    doc_id: int,
    n: int,
    user_ctx: UserCtx,
) -> DownloadableFile | None:
    """Historical-version lookup gated by `manageable_where` (story 26).

    `n` is the 1-based row_number ordering shared with `get_detail`. Any
    out-of-range value returns `None`. The ordering (`ORDER BY id`) must match
    `get_detail`'s `version_rows` query.
    """
    where, params = manageable_where("d", user_ctx)
    # ADR-0011 §4: only versions that were at some point the public current
    # (first_published_at IS NOT NULL) are downloadable here. Failed, discarded,
    # and in-flight ready candidates uniformly resolve to None → 404. The filter
    # lives in the subquery so the row_number() ordering (shared with get_detail)
    # is computed over the same narrowed set.
    row = (
        await session.execute(
            text(
                "SELECT encode(v.sha256, 'hex') AS sha, "
                "       v.original_filename, v.mime "
                "FROM documents d "
                "JOIN ("
                "  SELECT doc_id, sha256, original_filename, mime, "
                "         row_number() OVER (PARTITION BY doc_id ORDER BY id) AS n "
                "  FROM document_versions "
                "  WHERE doc_id = :doc_id AND first_published_at IS NOT NULL"
                ") v ON v.doc_id = d.id "
                f"WHERE d.id = :doc_id AND v.n = :n AND ({where})"
            ),
            {"doc_id": doc_id, "n": n, **params},
        )
    ).first()
    if row is None:
        return None
    return DownloadableFile(
        sha_hex=row.sha, original_filename=row.original_filename, mime=row.mime
    )
