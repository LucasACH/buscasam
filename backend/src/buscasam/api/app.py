"""FastAPI app factory and lifespan (ADR-0003 §1, §2, §8)."""
from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse

from buscasam.api.areas import router as areas_router
from buscasam.api.auth import auth_router, router as me_router
from buscasam.api.search import router as search_router
from buscasam.core import auth
from buscasam.settings import settings


UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class OriginCheckMiddleware(BaseHTTPMiddleware):
    """CSRF defense-in-depth (ADR-0005 §15, module map §Origin-check middleware).

    Reject unsafe methods carrying a `sid` cookie when `Origin` is missing or
    is not exactly `settings.base_url`. Reads the cookie but does not validate
    it — auth correctness is `current_user`'s job.
    """

    async def dispatch(self, request, call_next):
        if (
            request.method in UNSAFE_METHODS
            and request.cookies.get(auth.SID_COOKIE)
            and request.headers.get("origin") != settings.base_url
        ):
            return PlainTextResponse("Origin mismatch", status_code=403)
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = create_async_engine(settings.database_url)
    app.state.engine = engine
    app.state.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    app.state.tei = httpx.AsyncClient(base_url=settings.tei_url)
    try:
        yield
    finally:
        await app.state.tei.aclose()
        await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    app.add_middleware(OriginCheckMiddleware)
    app.include_router(search_router)
    app.include_router(areas_router)
    app.include_router(auth_router)
    app.include_router(me_router)
    return app
