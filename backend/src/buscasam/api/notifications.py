"""HTTP surface over the `notifications` table (module map §`api/notifications`).

SQL stays inline here per the PRD until a second caller earns extraction.
Every query is owner-scoped (`WHERE user_id = :uid`); cross-user access is
indistinguishable from a missing row (404, never 403).
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.api.deps import get_session
from buscasam.core import auth

router = APIRouter(prefix="/api/notifications")


class NotificationDTO(BaseModel):
    id: int
    kind: str
    payload: dict[str, object]
    read_at: datetime | None
    created_at: datetime


class NotificationsResponse(BaseModel):
    items: list[NotificationDTO]


class UnreadCountResponse(BaseModel):
    count: int


class MarkReadResponse(BaseModel):
    id: int
    read_at: datetime


class MarkAllReadResponse(BaseModel):
    count: int


@router.get("", response_model=NotificationsResponse)
async def list_notifications(
    user_ctx: auth.UserCtx = Depends(auth.require_authenticated),
    session: AsyncSession = Depends(get_session),
) -> NotificationsResponse:
    rows = (
        await session.execute(
            text(
                "SELECT id, kind, payload_json AS payload, read_at, created_at "
                "FROM notifications WHERE user_id = :uid "
                "ORDER BY created_at DESC, id DESC"
            ),
            {"uid": user_ctx.user_id},
        )
    ).mappings()
    return NotificationsResponse(items=[NotificationDTO(**r) for r in rows])


@router.get("/unread_count", response_model=UnreadCountResponse)
async def unread_count(
    user_ctx: auth.UserCtx = Depends(auth.require_authenticated),
    session: AsyncSession = Depends(get_session),
) -> UnreadCountResponse:
    count = (
        await session.execute(
            text(
                "SELECT count(*) FROM notifications "
                "WHERE user_id = :uid AND read_at IS NULL"
            ),
            {"uid": user_ctx.user_id},
        )
    ).scalar_one()
    return UnreadCountResponse(count=count)


@router.post("/{notification_id}/read", response_model=MarkReadResponse)
async def mark_read(
    notification_id: int = Path(...),
    user_ctx: auth.UserCtx = Depends(auth.require_authenticated),
    session: AsyncSession = Depends(get_session),
) -> MarkReadResponse:
    # COALESCE keeps the first read_at on re-mark (idempotent); the user_id
    # predicate makes another user's row indistinguishable from a missing one.
    row = (
        await session.execute(
            text(
                "UPDATE notifications SET read_at = COALESCE(read_at, now()) "
                "WHERE id = :id AND user_id = :uid "
                "RETURNING id, read_at"
            ),
            {"id": notification_id, "uid": user_ctx.user_id},
        )
    ).mappings().first()
    if row is None:
        raise HTTPException(status_code=404)
    return MarkReadResponse(**row)


@router.post("/mark_all_read", response_model=MarkAllReadResponse)
async def mark_all_read(
    user_ctx: auth.UserCtx = Depends(auth.require_authenticated),
    session: AsyncSession = Depends(get_session),
) -> MarkAllReadResponse:
    result = await session.execute(
        text(
            "UPDATE notifications SET read_at = now() "
            "WHERE user_id = :uid AND read_at IS NULL"
        ),
        {"uid": user_ctx.user_id},
    )
    return MarkAllReadResponse(count=result.rowcount)
