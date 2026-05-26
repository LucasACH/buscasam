"""FastAPI dependency-injected resources (ADR-0003 §2, §8)."""
from __future__ import annotations

import httpx
from fastapi import Request

from buscasam.core.db import get_session

__all__ = ["get_session", "get_tei_client"]


async def get_tei_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.tei
