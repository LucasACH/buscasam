"""Co-author invite, revoke, accept, and decline transitions
(module map §coauthor-invitations)."""
from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.core import notifications

from buscasam.core.documents._shared import _assert_owner
from buscasam.core.documents.exceptions import (
    CoauthorAlreadyListed,
    CoauthorNotPending,
    InvalidCoauthorId,
    InvitationNotPending,
)

if TYPE_CHECKING:
    from buscasam.core.auth import UserCtx


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

    await session.execute(
        text(
            "DELETE FROM notifications "
            "WHERE user_id = :uid AND event_key = :ek"
        ),
        {
            "uid": invitee_user_id,
            "ek": notifications.coauthor_invite_event_key(doc_id, invitee_user_id),
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

    await session.execute(
        text(
            "UPDATE notifications SET read_at = now() "
            "WHERE user_id = :uid AND event_key = :ek"
        ),
        {
            "uid": user_ctx.user_id,
            "ek": notifications.coauthor_invite_event_key(doc_id, user_ctx.user_id),
        },
    )
