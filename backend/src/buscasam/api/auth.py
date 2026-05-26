"""HTTP surface over `core/auth`. URL + HTTP semantics live here.

Per module map §`api/auth`: this router orchestrates `core/auth` primitives;
it never opens transactions, queries `users`/`sessions` directly, or touches
`oauth_state` beyond reading the cookie value to forward.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.api.deps import get_session
from buscasam.core import auth

router = APIRouter(prefix="/api")
auth_router = APIRouter(prefix="/api/auth")


class MeResponse(BaseModel):
    user_id: int
    role: str
    name: str
    picture_url: str | None
    hd: str


@auth_router.get("/login")
async def login(next: str | None = Query(default=None)) -> RedirectResponse:
    return await auth.begin_login(next)


@auth_router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    _: auth.UserCtx = Depends(auth.require_authenticated),
    session: AsyncSession = Depends(get_session),
) -> Response:
    await auth.end_session(
        session,
        sid_cookie=request.cookies.get(auth.SID_COOKIE),
        response=response,
    )
    response.status_code = 204
    return response


@auth_router.get("/google/callback")
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


@router.get("/me", response_model=MeResponse)
async def me(
    user_ctx: auth.UserCtx = Depends(auth.require_authenticated),
    session: AsyncSession = Depends(get_session),
) -> MeResponse:
    row = (
        await session.execute(
            text(
                "SELECT role, name, picture_url, hd "
                "FROM users WHERE id = :uid"
            ),
            {"uid": user_ctx.user_id},
        )
    ).mappings().first()
    if row is None:  # session row referenced a now-deleted user
        raise HTTPException(status_code=401)
    return MeResponse(user_id=user_ctx.user_id, **row)
