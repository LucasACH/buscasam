"""GET /api/search — hybrid retrieval with silent lexical fallback (slice 5)."""
from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import date
from typing import Literal

import httpx
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.api.deps import get_session, get_tei_client
from buscasam.core import search_query
from buscasam.core.embed import EmbedUnavailable, embed
from buscasam.core.search_query import Orden
from buscasam.settings import settings

logger = logging.getLogger("buscasam.search")

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

RELEVANCE_PAGE_CAP = 20


class ResultDTO(BaseModel):
    doc_id: int
    titulo: str
    fecha: date
    area_path: str
    tipo: str
    abstract: str | None
    snippet: str
    snippet_is_html: bool


class SearchResponse(BaseModel):
    results: list[ResultDTO]
    total: int
    saturated: bool
    unfiltered_total: int | None = None
    lexical_fallback: bool = False


async def _embed_or_fallback(
    tei: httpx.AsyncClient, q: str
) -> tuple[np.ndarray | None, bool]:
    try:
        return await embed(tei, q, kind="query"), False
    except EmbedUnavailable:
        return None, True


@router.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query(default=""),
    pagina: int = Query(default=1, ge=1),
    area: str | None = Query(default=None, pattern=r"^[a-z0-9_]+(\.[a-z0-9_]+)*$"),
    tipo: list[Tipo] = Query(default_factory=list),
    desde: int | None = Query(default=None, ge=1000, le=9999),
    hasta: int | None = Query(default=None, ge=1000, le=9999),
    orden: Orden = Query(default="relevancia"),
    session: AsyncSession = Depends(get_session),
    tei: httpx.AsyncClient = Depends(get_tei_client),
) -> SearchResponse:
    if orden == "relevancia" and not q:
        raise HTTPException(
            status_code=422, detail="q is required when orden=relevancia"
        )
    if orden == "relevancia" and pagina > RELEVANCE_PAGE_CAP:
        raise HTTPException(
            status_code=422,
            detail=f"pagina must be <= {RELEVANCE_PAGE_CAP} under orden=relevancia",
        )
    if desde is not None and hasta is not None and desde > hasta:
        raise HTTPException(status_code=422, detail="desde must be <= hasta")
    if orden == "recientes":
        embedding, fallback = None, False
    else:
        embedding, fallback = await _embed_or_fallback(tei, q)
        logger.info(
            "lexical_fallback_rate",
            extra={"fallback": fallback, "q_len": len(q)},
        )
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
            orden=orden,
        ),
        user_ctx=user_ctx,
        embedding=embedding,
        min_semantic_similarity=settings.min_semantic_similarity,
    )
    has_filter = area is not None or bool(tipo) or desde is not None or hasta is not None
    unfiltered_total: int | None = None
    if has_filter:
        unfiltered = await search_query.run(
            session,
            filters=search_query.Filters(q=q, pagina=1, orden=orden),
            user_ctx=user_ctx,
            embedding=embedding,
            min_semantic_similarity=settings.min_semantic_similarity,
        )
        unfiltered_total = unfiltered.total
    return SearchResponse(
        results=[ResultDTO(**asdict(r)) for r in result.rows],
        total=result.total,
        saturated=result.saturated,
        unfiltered_total=unfiltered_total,
        lexical_fallback=fallback,
    )
