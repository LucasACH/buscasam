"""Draft creation, metadata edits, and the editar-form / mis-trabajos
projections (module map §core/documents)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING, Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.core.document_access import manageable_where

from buscasam.core.documents._shared import (
    UNSET,
    DetailVersion,
    _Unset,
    _assert_owner,
    _published_version_history,
    _to_detail_version,
    assert_manageable,
)
from buscasam.core.documents.exceptions import DocumentNotFound, InvalidCoauthorId

if TYPE_CHECKING:
    from buscasam.core.auth import UserCtx


CoauthorStatus = Literal["owner", "pending", "accepted", "declined", "external"]


@dataclass(frozen=True)
class AttachmentInfo:
    id: int
    original_filename: str
    size_bytes: int
    mime: str | None


@dataclass(frozen=True)
class ExternalAuthor:
    name: str
    surname: str
    email: str


@dataclass(frozen=True)
class CoauthorRow:
    user_id: int | None
    display_name: str
    email_local: str | None
    email: str | None
    status: CoauthorStatus


@dataclass(frozen=True)
class CandidateState:
    """In-flight replacement candidate projection for the editar CandidatePanel
    (module map §core/documents, ADR-0011 §9). `status` is the raw lifecycle
    collapsed to the three UI states; the Spanish labels live on the frontend."""
    status: Literal["processing", "ready", "failed"]
    index_stage: str | None  # pipeline checkpoint while status='processing'
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
    index_stage: str | None
    staged_abstract: str | None
    staged_keywords: list[str]
    staged_fecha: date | None
    generated_abstract: str | None
    generated_keywords: list[str]
    generated_fecha: date | None
    index_error: str | None
    publish_gate_reason: str | None
    is_owner: bool
    visibility: str
    area_path: str
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
    moderation_hidden: bool


async def create_draft(
    session: AsyncSession,
    user_ctx: UserCtx,
    *,
    title: str,
    area_path: str,
    document_type: str,
    visibility: str,
    external_authors: list[ExternalAuthor],
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

    for external in external_authors:
        await session.execute(
            text(
                "INSERT INTO document_authors (doc_id, user_id, display_name, email, status) "
                "VALUES (:doc_id, NULL, :name, :email, 'external')"
            ),
            {
                "doc_id": doc_id,
                "name": f"{external.name} {external.surname}".strip(),
                "email": external.email,
            },
        )

    return doc_id


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
    """Writes top-level fields to `documents` and staged_* to the published
    current version plus any in-flight candidate, enqueuing refresh_headline per
    version when title or abstract changed (module map §core/documents). Frozen
    historical versions and a discarded candidate are left untouched.
    Manageable-scoped; cross-user → DocumentNotFound. Visibility is owner-only
    (ADR-0010 §8): an accepted coauthor passing `visibility` → NotOwner."""
    await assert_manageable(session, user_ctx, doc_id)
    if visibility is not None:
        await _assert_owner(session, user_ctx, doc_id)

    # Edit-relevant versions: the published current (is_current) and the
    # never-published candidate (first_published_at IS NULL). A discarded
    # candidate and frozen historical versions (first_published_at set, not
    # current) are excluded — their staged_* must not move and they get no
    # reindex. Pre-update staged_abstract drives per-version change detection.
    rows = (
        await session.execute(
            text(
                "SELECT v.id AS version_id, v.index_status, v.staged_abstract, "
                "       d.titulo "
                "FROM document_versions v JOIN documents d ON d.id = v.doc_id "
                "WHERE v.doc_id = :doc_id AND v.index_status <> 'discarded' "
                "  AND (v.is_current = true OR v.first_published_at IS NULL)"
            ),
            {"doc_id": doc_id},
        )
    ).mappings().all()

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

    if not rows:
        return
    # titulo is shared across versions (joined from documents), so the change is
    # the same for every row; the two headline reindexes are independent per
    # ADR-0008 §3 (`headline:v{id}` locks).
    title_changed = title is not None and title != rows[0]["titulo"]

    for row in rows:
        version_id = row["version_id"]
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
                    f"UPDATE document_versions SET {', '.join(ver_sets)} "
                    "WHERE id = :vid"
                ),
                ver_params,
            )

        # Reindex only when a headline input actually changed AND this version is
        # already indexed: while still processing, index_document builds the
        # headline from the current title, so a concurrent refresh would
        # duplicate it.
        abstract_changed = abstract is not None and abstract != (
            row["staged_abstract"] or ""
        )
        if row["index_status"] == "indexed" and (title_changed or abstract_changed):
            from buscasam.core import jobs

            await jobs.enqueue_refresh_headline(session, version_id)


async def get_draft_state(
    session: AsyncSession, user_ctx: UserCtx, doc_id: int
) -> DraftState:
    await assert_manageable(session, user_ctx, doc_id)
    row = (
        await session.execute(
            text(
                "SELECT v.id AS version_id, v.index_status, v.index_stage, "
                "       v.staged_abstract, "
                "       v.staged_keywords, v.staged_fecha, v.index_error, "
                "       v.generated_abstract, v.generated_keywords, "
                "       v.generated_fecha, "
                "       v.headline_fingerprint, d.titulo, d.visibility, "
                "       d.area_path::text AS area_path, "
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
    # one projection (_published_version_history) so both stay aligned.
    version_history = await _published_version_history(session, doc_id)
    # ADR-0011 §9: the in-flight replacement candidate, if any. The partial
    # unique index admits at most one (never-public, non-discarded, non-current)
    # row, so one_or_none is the contract, not a LIMIT.
    is_owner = row["owner_user_id"] == user_ctx.user_id
    cand_row = (
        await session.execute(
            text(
                "SELECT v.index_status, v.index_stage, v.staged_abstract, "
                "       v.staged_keywords, "
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
            index_stage=cand_row["index_stage"],
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
                "SELECT da.user_id, da.display_name, da.status, da.email, "
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
        index_stage=row["index_stage"],
        staged_abstract=row["staged_abstract"],
        staged_keywords=row["staged_keywords"] or [],
        staged_fecha=row["staged_fecha"],
        generated_abstract=row["generated_abstract"],
        generated_keywords=row["generated_keywords"] or [],
        generated_fecha=row["generated_fecha"],
        index_error=row["index_error"],
        publish_gate_reason=_publish_gate_reason(
            row["index_status"], matches
        ),
        is_owner=is_owner,
        visibility=row["visibility"],
        area_path=row["area_path"],
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
                email=c["email"],
                status=c["status"],
            )
            for c in coauthor_rows
        ],
        versions=[_to_detail_version(v) for v in version_history],
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
                f"       d.published_at, "
                f"       d.moderation_hidden_at IS NOT NULL AS moderation_hidden "
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
            moderation_hidden=r["moderation_hidden"],
        )
        for r in rows
    ]
