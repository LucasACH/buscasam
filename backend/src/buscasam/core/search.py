"""Search orchestration: embed→fallback, retrieval, optional unfiltered count.

Owns the policy seams that don't belong in `core/search_query` (SQL) or the
HTTP route (URL shape): silent lexical fallback on TEI failure (ADR-0002 §8)
and the "second call with filters dropped" rule for unfiltered_total.
Future authenticated routes call the same `execute`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, replace

import httpx
import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.core import search_query
from buscasam.core.embed import EmbedUnavailable, embed
from buscasam.core.search_query import Filters, ResultRow, UserCtx

logger = logging.getLogger("buscasam.search")


@dataclass(frozen=True)
class ExecuteResult:
    rows: list[ResultRow]
    total: int
    saturated: bool
    unfiltered_total: int | None
    lexical_fallback: bool


def _has_filter(filters: Filters) -> bool:
    return (
        filters.area_path is not None
        or bool(filters.tipos)
        or filters.desde is not None
        or filters.hasta is not None
    )


async def _embed_or_fallback(
    tei: httpx.AsyncClient, q: str
) -> tuple[np.ndarray | None, bool]:
    try:
        return await embed(tei, q, kind="query"), False
    except EmbedUnavailable:
        return None, True


async def execute(
    session: AsyncSession,
    tei: httpx.AsyncClient,
    *,
    filters: Filters,
    user_ctx: UserCtx,
    min_semantic_similarity: float,
) -> ExecuteResult:
    if filters.orden == "recientes":
        embedding: np.ndarray | None = None
        lexical_fallback = False
    else:
        embedding, lexical_fallback = await _embed_or_fallback(tei, filters.q)
        logger.info(
            "lexical_fallback_rate",
            extra={"fallback": lexical_fallback, "q_len": len(filters.q)},
        )

    result = await search_query.run(
        session,
        filters=filters,
        user_ctx=user_ctx,
        embedding=embedding,
        min_semantic_similarity=min_semantic_similarity,
    )

    unfiltered_total: int | None = None
    if _has_filter(filters):
        unfiltered = await search_query.run(
            session,
            filters=replace(
                filters,
                pagina=1,
                area_path=None,
                tipos=(),
                desde=None,
                hasta=None,
            ),
            user_ctx=user_ctx,
            embedding=embedding,
            min_semantic_similarity=min_semantic_similarity,
        )
        unfiltered_total = unfiltered.total

    return ExecuteResult(
        rows=result.rows,
        total=result.total,
        saturated=result.saturated,
        unfiltered_total=unfiltered_total,
        lexical_fallback=lexical_fallback,
    )
