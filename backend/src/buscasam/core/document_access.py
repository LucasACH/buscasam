"""Sole owner of "what counts as a readable document" — ADR-0010 §6."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from buscasam.core.auth import UserCtx


def invitado_where(alias: str) -> str:
    """`WHERE`-clause body restricting reads to the invitado branch.

    `alias` is the SQL name (table name or alias) under which the `documents`
    table is in scope at the call site — passed explicitly so this module owns
    column qualification.

    See module map § `core/document_access` and ADR-0010 §6.

    Predicate text must stay aligned with migration 0007's partial index
    (`documents_publico_recientes`) — see comment there.
    """
    return (
        f"{alias}.visibility = 'publico' "
        f"AND {alias}.publication_status = 'published' "
        f"AND {alias}.soft_deleted_at IS NULL "
        f"AND {alias}.moderation_hidden_at IS NULL"
    )


def readable_where(alias: str, user_ctx: UserCtx) -> tuple[str, dict]:
    """`WHERE`-clause body + bind params for the normal readable predicate.

    Implements ADR-0010 §7 across all three visibility tiers and the coauthor
    predicate: a published, non-deleted, non-hidden document is readable when
    it is `publico`, or `interno` and the reader is UNSAM, or the reader is an
    `owner`/`accepted` author. `pending` invitees are excluded by construction.

    `alias` is the SQL name under which `documents` is in scope at the call
    site; the returned `{"user_id", "is_unsam"}` params must be merged into the
    statement bindings. The sole owner of authenticated document reads
    (search, detail, related) — see module map § `core/document_access`.
    """
    where = (
        f"{alias}.publication_status = 'published' "
        f"AND {alias}.soft_deleted_at IS NULL "
        f"AND {alias}.moderation_hidden_at IS NULL "
        f"AND ("
        f"{alias}.visibility = 'publico' "
        f"OR ({alias}.visibility = 'interno' AND :is_unsam) "
        f"OR EXISTS ("
        f"SELECT 1 FROM document_authors da "
        f"WHERE da.doc_id = {alias}.id "
        f"AND da.user_id = :user_id "
        f"AND da.status IN ('owner', 'accepted')"
        f")"
        f")"
    )
    return where, {"user_id": user_ctx.user_id, "is_unsam": user_ctx.is_unsam}


def pending_invitation_disclosure_where(
    alias: str, user_ctx: UserCtx
) -> tuple[str, dict]:
    """`WHERE`-clause body + bind params for the ADR-0010 §6 disclosure carve-out.

    Recipient-scoped, **not** visibility-scoped: a `pending` invitee matches on a
    privado, interno, or publico document alike (the visibility tier only governs
    what the router composes around the banner). The source document must be
    published, non-deleted, and non-hidden — a pending invitee gets no disclosure
    for a soft-deleted or moderation-hidden document (PRD stories 32-33).

    `user_ctx.user_id` is required by construction — invitados cannot be
    invitees, so there is no row to match; callers must guard or use
    `require_authenticated` upstream.
    """
    if user_ctx.user_id is None:
        raise ValueError("pending_invitation_disclosure_where requires an authenticated user")
    where = (
        f"{alias}.publication_status = 'published' "
        f"AND {alias}.soft_deleted_at IS NULL "
        f"AND {alias}.moderation_hidden_at IS NULL "
        f"AND EXISTS ("
        f"SELECT 1 FROM document_authors da "
        f"WHERE da.doc_id = {alias}.id "
        f"AND da.user_id = :user_id "
        f"AND da.status = 'pending'"
        f")"
    )
    return where, {"user_id": user_ctx.user_id}


def manageable_where(alias: str, user_ctx: UserCtx) -> tuple[str, dict]:
    """`WHERE`-clause body + bind params for the author-management predicate.

    Returns documents where `user_ctx` is an `owner` or `accepted` coauthor
    (ADR-0010 §8). Drafts and published documents both qualify; soft-deleted
    are excluded. No visibility filter — manageable scope is author-scoped,
    not visibility-scoped.
    """
    where = (
        f"{alias}.soft_deleted_at IS NULL "
        f"AND EXISTS ("
        f"SELECT 1 FROM document_authors da "
        f"WHERE da.doc_id = {alias}.id "
        f"AND da.user_id = :mgmt_user_id "
        f"AND da.status IN ('owner', 'accepted')"
        f")"
    )
    return where, {"mgmt_user_id": user_ctx.user_id}
