"""HTTP surface over `core/auth`. URL + HTTP semantics live here.

Per module map §`api/auth`: this router orchestrates `core/auth` primitives;
it never opens transactions, queries `users`/`sessions` directly, or touches
`oauth_state` beyond reading the cookie value to forward.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.api.deps import get_session
from buscasam.core import auth

router = APIRouter(prefix="/api/auth")


@router.get("/login")
async def login(next: str | None = Query(default=None)) -> RedirectResponse:
    return await auth.begin_login(next)


@router.get("/google/callback")
async def google_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    return await auth.complete_login(
        code=code,
        state_param=state,
        state_cookie=request.cookies.get(auth.STATE_COOKIE, ""),
        session=session,
    )
