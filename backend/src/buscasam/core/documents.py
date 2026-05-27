"""Domain chokepoint for all document mutations and queries (ADR-0010 §6, module map §core/documents)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING

import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.core.document_access import manageable_where
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


class AttachmentCapExceeded(Exception):
    """The document already holds the maximum of 5 attachments (→ 409)."""


@dataclass(frozen=True)
class AttachmentInfo:
    id: int
    original_filename: str
    size_bytes: int
    mime: str | None


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
    """ADR-0010 §9: insert a unique-keyed processing_failed notification."""
    cv = await load_candidate(session, version_id)
    await session.execute(
        text(
            "UPDATE document_versions SET index_status = 'failed', "
            "  index_error = :err WHERE id = :id"
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
    await session.execute(
        text("UPDATE document_versions SET is_current = true WHERE id = :v"),
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

    # No-op stub at this PRD's window; PRD #5 fills the fan-out (module map).
    from buscasam.core import jobs

    await jobs.enqueue_fan_out_coauthor_invites(session, doc_id)


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
        is_owner=row["owner_user_id"] == user_ctx.user_id,
        attachments=[
            AttachmentInfo(
                id=a["id"],
                original_filename=a["original_filename"],
                size_bytes=a["bytes"],
                mime=a["mime"],
            )
            for a in att_rows
        ],
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
