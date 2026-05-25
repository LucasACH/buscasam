"""GET /api/search — lexical-only retrieval for the invitado branch (slice 2)."""
from __future__ import annotations

from dataclasses import asdict
from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.api.deps import get_session
from buscasam.core import search_query

router = APIRouter(prefix="/api")


class ResultDTO(BaseModel):
    doc_id: int
    titulo: str
    fecha: date
    area_path: str
    tipo: str
    abstract: str | None
    snippet: str


class SearchResponse(BaseModel):
    results: list[ResultDTO]
    total: int
    saturated: bool


@router.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query(min_length=1),
    pagina: int = Query(default=1, ge=1, le=20),
    session: AsyncSession = Depends(get_session),
) -> SearchResponse:
    result = await search_query.run(
        session,
        filters=search_query.Filters(q=q, pagina=pagina),
        user_ctx=search_query.UserCtx(role="invitado"),
    )
    return SearchResponse(
        results=[ResultDTO(**asdict(r)) for r in result.rows],
        total=result.total,
        saturated=result.saturated,
    )
