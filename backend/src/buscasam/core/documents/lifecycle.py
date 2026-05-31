"""Soft-delete, restore, and the Papelera projection
(module map §deletion-restoration-purge)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.core.document_access import restorable_where

from buscasam.core.documents.exceptions import DocumentNotFound

if TYPE_CHECKING:
    from buscasam.core.auth import UserCtx


@dataclass(frozen=True)
class DeletedDocSummary:
    id: int
    title: str
    publication_status: str  # draft | published — for the Papelera label
    soft_deleted_at: datetime
    purge_at: datetime  # soft_deleted_at + 180 días, computed server-side


async def soft_delete(
    session: AsyncSession, user_ctx: UserCtx, doc_id: int
) -> None:
    """Owner-only logical deletion (module map §core/documents, issue #65).

    Owner-only via the `publish` inline-owner-SELECT precedent: a missing row or
    a non-owner (accepted coautor or stranger) raises DocumentNotFound — the two
    are indistinguishable, so there is no existence leak. The owner SELECT
    carries no moderation_hidden_at and no soft_deleted_at filter, so a
    moderation-hidden document is still deletable and an already-deleted document
    still passes the gate.

    Stamp-once clock: the UPDATE only matches a row whose soft_deleted_at IS
    NULL, so re-deleting is a harmless no-op that never moves the timestamp — the
    180-día retention window counts from the first deletion. Touches neither
    publication_status nor moderation_hidden_at; the lifecycle lives entirely in
    soft_deleted_at (ADR-0010 §10, ADR-0006 §11). The inherited exclusion
    (soft_deleted_at IS NULL in every read predicate) makes the document
    immediately invisible to every reader surface.
    """
    owner_user_id = (
        await session.execute(
            text(
                "SELECT user_id FROM document_authors "
                "WHERE doc_id = :doc_id AND status = 'owner' LIMIT 1"
            ),
            {"doc_id": doc_id},
        )
    ).scalar_one_or_none()
    if owner_user_id is None or owner_user_id != user_ctx.user_id:
        raise DocumentNotFound

    await session.execute(
        text(
            "UPDATE documents SET soft_deleted_at = now() "
            "WHERE id = :doc_id AND soft_deleted_at IS NULL"
        ),
        {"doc_id": doc_id},
    )


async def restore(
    session: AsyncSession, user_ctx: UserCtx, doc_id: int
) -> None:
    """Owner-only undo of a soft-delete (module map §core/documents, issue #66).

    Clears soft_deleted_at on the caller's OWN soft-deleted document. The UPDATE
    is gated by restorable_where, so a live document, a non-owner, or another
    user's deleted document all match zero rows → DocumentNotFound (→ 404, no
    existence leak; stories 12, 20).

    A true undo with nothing to reconstruct: delete only hid the row via the
    inherited soft_deleted_at IS NULL exclusion, so the current-version flag,
    publication_status, attachments, and coautores were never mutated — clearing
    the timestamp returns the document to exactly its prior state (stories 8-11).
    """
    where, params = restorable_where("d", user_ctx)
    result = await session.execute(
        text(
            f"UPDATE documents AS d SET soft_deleted_at = NULL "
            f"WHERE d.id = :doc_id AND ({where})"
        ),
        params | {"doc_id": doc_id},
    )
    if result.rowcount == 0:
        raise DocumentNotFound


async def list_deleted_documents(
    session: AsyncSession, user_ctx: UserCtx
) -> list[DeletedDocSummary]:
    """The Papelera projection — sibling of list_own_documents, gated by
    restorable_where instead of manageable_where (module map §core/documents,
    issue #66). Returns only the caller's own soft-deleted documents, ordered by
    soft_deleted_at desc. purge_at is `soft_deleted_at + INTERVAL '180 days'`
    projected in SQL, so the 180-día retention constant is single-sourced
    server-side; the client derives the days-remaining label from it."""
    where, params = restorable_where("d", user_ctx)
    rows = (
        await session.execute(
            text(
                f"SELECT d.id, d.titulo, d.publication_status, d.soft_deleted_at, "
                f"       d.soft_deleted_at + INTERVAL '180 days' AS purge_at "
                f"FROM documents d WHERE {where} "
                f"ORDER BY d.soft_deleted_at DESC"
            ),
            params,
        )
    ).mappings().all()
    return [
        DeletedDocSummary(
            id=r["id"],
            title=r["titulo"],
            publication_status=r["publication_status"],
            soft_deleted_at=r["soft_deleted_at"],
            purge_at=r["purge_at"],
        )
        for r in rows
    ]
