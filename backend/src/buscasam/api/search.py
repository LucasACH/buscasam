"""GET /api/search — lexical-only retrieval for the invitado branch (slice 2)."""
from __future__ import annotations

from dataclasses import asdict
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.api.deps import get_session
from buscasam.core import search_query

router = APIRouter(prefix="/api")

Tipo = Literal[
    "tesis",
    "paper",
    "trabajo_practico",
    "proyecto_investigacion",
    "monografia",
    "ponencia_poster",
    "apunte_resumen",
    "informe_catedra",
]


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
    unfiltered_total: int | None = None


@router.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query(min_length=1),
    pagina: int = Query(default=1, ge=1, le=20),
    area: str | None = Query(default=None, pattern=r"^[a-z0-9_]+(\.[a-z0-9_]+)*$"),
    tipo: list[Tipo] = Query(default_factory=list),
    desde: int | None = Query(default=None, ge=1000, le=9999),
    hasta: int | None = Query(default=None, ge=1000, le=9999),
    session: AsyncSession = Depends(get_session),
) -> SearchResponse:
    if desde is not None and hasta is not None and desde > hasta:
        raise HTTPException(status_code=422, detail="desde must be <= hasta")
    user_ctx = search_query.UserCtx(role="invitado")
    result = await search_query.run(
        session,
        filters=search_query.Filters(
            q=q,
            pagina=pagina,
            area_path=area,
            tipos=tuple(tipo),
            desde=desde,
            hasta=hasta,
        ),
        user_ctx=user_ctx,
    )
    has_filter = area is not None or bool(tipo) or desde is not None or hasta is not None
    unfiltered_total: int | None = None
    if has_filter:
        unfiltered = await search_query.run(
            session,
            filters=search_query.Filters(q=q, pagina=1),
            user_ctx=user_ctx,
        )
        unfiltered_total = unfiltered.total
    return SearchResponse(
        results=[ResultDTO(**asdict(r)) for r in result.rows],
        total=result.total,
        saturated=result.saturated,
        unfiltered_total=unfiltered_total,
    )
