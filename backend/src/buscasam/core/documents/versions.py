"""Main-version upload, replacement, and candidate discard (ADR-0011,
module map §version-replacement)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.core.document_access import manageable_where

from buscasam.core.documents._shared import assert_manageable
from buscasam.core.documents.exceptions import (
    DocumentNotFound,
    NoCandidateToDiscard,
    NoPublishedVersion,
)

if TYPE_CHECKING:
    from buscasam.core.auth import UserCtx
    from buscasam.core.blob_store import BlobPutResult


@dataclass(frozen=True)
class CandidateVersion:
    version_id: int
    doc_id: int
    sha256: str
    mime: str
    title: str
    owner_user_id: int | None


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


async def discard_candidate(
    session: AsyncSession, user_ctx: UserCtx, doc_id: int
) -> None:
    """Explicit descartar of the in-flight replacement candidate (module map
    §core/documents, ADR-0011 §9). Manageable-scoped; cross-user →
    DocumentNotFound. Selects the candidate (is_current=false,
    index_status<>'discarded', never-public) FOR UPDATE — the same predicate the
    `document_versions_one_candidate` index admits, so at most one row matches —
    and raises NoCandidateToDiscard when none. Sets index_status='discarded' and
    deletes that version's chunks (always is_current=false, so search visibility
    is unchanged). Leaves the document_versions row and the blob (orphan sweep
    handles blob cleanup).

    Liveness: the worker no longer holds the candidate row lock across its
    extract/OCR IO. `jobs._claim` commits the pending→processing flip in a short
    transaction, releasing `_begin_indexing`'s FOR UPDATE before the IO begins,
    and finalizes through the `WHERE index_status='processing'` guard (ADR-0011
    §5). So this FOR UPDATE contends only with the brief claim and finalize
    transactions, not the IO window — descartar commits while indexing work is
    in flight, and the worker's guarded write then no-ops against the discarded
    row. The only remaining wait is the sub-second overlap with claim/finalize."""
    await assert_manageable(session, user_ctx, doc_id)
    candidate_vid = (
        await session.execute(
            text(
                "SELECT id FROM document_versions "
                "WHERE doc_id = :doc_id AND is_current = false "
                "  AND index_status <> 'discarded' AND first_published_at IS NULL "
                "FOR UPDATE"
            ),
            {"doc_id": doc_id},
        )
    ).scalar_one_or_none()
    if candidate_vid is None:
        raise NoCandidateToDiscard
    await session.execute(
        text(
            "UPDATE document_versions SET index_status = 'discarded' WHERE id = :id"
        ),
        {"id": candidate_vid},
    )
    await session.execute(
        text("DELETE FROM chunks WHERE version_id = :id"),
        {"id": candidate_vid},
    )


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
