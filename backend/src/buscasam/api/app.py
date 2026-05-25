"""FastAPI app factory and lifespan (ADR-0003 §1, §2, §8)."""
from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from buscasam.api.areas import router as areas_router
from buscasam.api.search import router as search_router
from buscasam.settings import settings


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
    app.include_router(search_router)
    app.include_router(areas_router)
    return app
