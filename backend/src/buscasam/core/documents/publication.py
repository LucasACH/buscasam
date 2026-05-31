"""Atomic staged → current publish flip (module map §document-publication)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.core.documents.exceptions import DocumentNotFound, PublishConflict

if TYPE_CHECKING:
    from buscasam.core.auth import UserCtx


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
