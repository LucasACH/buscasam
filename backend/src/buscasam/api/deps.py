"""FastAPI dependency-injected resources (ADR-0003 §2, §8)."""
from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    sessionmaker = request.app.state.sessionmaker
    async with sessionmaker() as session:
        yield session


async def get_tei_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.tei
