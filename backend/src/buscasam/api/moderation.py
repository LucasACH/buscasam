"""HTTP edge for the moderation flow (module map §api/moderation).

The single chokepoint where moderation access is gated: `require_authenticated`
for filing a report. Delegates to `core/moderation`; maps every domain miss to a
uniform 404 so hidden/private/deleted existence is never disclosed. Opens no
transactions and writes no tables directly.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.api.deps import get_session
from buscasam.core import auth
from buscasam.core.moderation import DocumentNotReadable, Reason, file_report

router = APIRouter(prefix="/api/moderation")


class ReportBody(BaseModel):
    doc_id: int
    reason: Reason


@router.post("/reports", status_code=204)
async def create_report(
    body: ReportBody,
    user_ctx: auth.UserCtx = Depends(auth.require_authenticated),
    session: AsyncSession = Depends(get_session),
) -> Response:
    try:
        await file_report(session, user_ctx, body.doc_id, body.reason)
    except DocumentNotReadable:
        raise HTTPException(status_code=404, detail="not_found")
    return Response(status_code=204)
