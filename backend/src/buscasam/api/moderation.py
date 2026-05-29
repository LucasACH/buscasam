"""HTTP edge for the moderation flow (module map §api/moderation).

The single chokepoint where moderation access is gated: `require_authenticated`
for filing a report, `require_docente` for the triage queue read. Delegates to
`core/moderation`; maps every domain miss to a uniform 404 so hidden/private/
deleted existence is never disclosed. Opens no transactions and writes no tables
directly — same envelope discipline as api/notifications.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.api.deps import get_session
from buscasam.core import auth
from buscasam.core.moderation import (
    DocumentNotReadable,
    Reason,
    file_report,
    list_open_reports,
)

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


class QueueEntryDTO(BaseModel):
    doc_id: int
    title: str
    reasons: list[str]
    first_reported_at: datetime
    last_reported_at: datetime
    report_count: int


class QueueResponse(BaseModel):
    items: list[QueueEntryDTO]


@router.get("/queue", response_model=QueueResponse)
async def queue(
    _docente: auth.UserCtx = Depends(auth.require_docente),
    session: AsyncSession = Depends(get_session),
) -> QueueResponse:
    entries = await list_open_reports(session)
    return QueueResponse(items=[QueueEntryDTO(**vars(e)) for e in entries])
