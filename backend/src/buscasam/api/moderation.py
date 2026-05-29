"""HTTP edge over the moderation lifecycle (module map §api/moderation).

This slice (issue #76) exposes only the Docente triage queue read; reporting,
inspection, and the hide/unhide/dismiss actions arrive in later slices. Opens no
transactions and writes no tables — same envelope discipline as api/notifications.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.api.deps import get_session
from buscasam.core import auth, moderation

router = APIRouter(prefix="/api/moderation")


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
    entries = await moderation.list_open_reports(session)
    return QueueResponse(items=[QueueEntryDTO(**vars(e)) for e in entries])
