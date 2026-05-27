"""HTTP edge for the two invitee-side invitation mutations (module map
§api/coauthor_invitations).

Both endpoints take the doc id from the URL and the invitee from
`current_user.user_id`, delegate to `core/documents`, and map every miss
(idempotent re-submit, owner-revoked, soft-deleted, moderation-hidden,
never-invited) to a uniform 404 — same envelope as `api/docs`. Never opens
transactions or touches `document_authors` / `notifications` directly.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.api.deps import get_session
from buscasam.core import auth
from buscasam.core.documents import (
    InvitationNotPending,
    accept_invitation,
    decline_invitation,
)

router = APIRouter(prefix="/api/coauthor_invitations")


@router.post("/{doc_id}/accept", status_code=204)
async def accept(
    doc_id: int,
    user_ctx: auth.UserCtx = Depends(auth.require_authenticated),
    session: AsyncSession = Depends(get_session),
) -> Response:
    try:
        await accept_invitation(session, user_ctx, doc_id)
    except InvitationNotPending:
        raise HTTPException(status_code=404, detail="not_found")
    return Response(status_code=204)


@router.post("/{doc_id}/decline", status_code=204)
async def decline(
    doc_id: int,
    user_ctx: auth.UserCtx = Depends(auth.require_authenticated),
    session: AsyncSession = Depends(get_session),
) -> Response:
    try:
        await decline_invitation(session, user_ctx, doc_id)
    except InvitationNotPending:
        raise HTTPException(status_code=404, detail="not_found")
    return Response(status_code=204)
