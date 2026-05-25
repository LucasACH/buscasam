"""FastAPI app factory and lifespan (ADR-0003 §1, §2, §8)."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from buscasam.api.search import router as search_router
from buscasam.settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = create_async_engine(settings.database_url)
    app.state.engine = engine
    app.state.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield
    finally:
        await engine.dispose()


app = FastAPI(lifespan=lifespan)
app.include_router(search_router)
