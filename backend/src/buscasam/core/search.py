"""Search orchestration: embed→fallback, retrieval, optional unfiltered count.

Owns the policy seams that don't belong in `core/search_query` (SQL) or the
HTTP route (URL shape): silent lexical fallback on TEI failure (ADR-0002 §8)
and the "second call with filters dropped" rule for unfiltered_total.
Future authenticated routes call the same `execute`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import httpx
import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.core import search_query
from buscasam.core.document_access import invitado_where
from buscasam.core.embed import EmbedUnavailable, embed
from buscasam.core.search_query import Filters, ResultRow

if TYPE_CHECKING:
    from buscasam.core.auth import UserCtx

logger = logging.getLogger("buscasam.search")


@dataclass(frozen=True)
class ExecuteResult:
    rows: list[ResultRow]
    total: int
    saturated: bool
    unfiltered_total: int | None
    lexical_fallback: bool
    fuzzy_fallback: bool


def _has_filter(filters: Filters) -> bool:
    return (
        filters.area_path is not None
        or bool(filters.tipos)
        or filters.desde is not None
        or filters.hasta is not None
    )


async def count_public_documents(session: AsyncSession) -> int:
    """The público catalog size for the landing footnote — the unfiltered público
    total under `core/document_access.invitado_where` (module map §core/search)."""
    return (
        await session.execute(
            text(f"SELECT count(*) FROM documents d WHERE {invitado_where('d')}")
        )
    ).scalar_one()


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
    fuzzy_word_similarity_threshold: float,
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

    # Typo-tolerant fallback: only when exact retrieval found nothing for a
    # relevance query. Replaces the empty result set if it surfaces anything.
    fuzzy_fallback = False
    if result.total == 0 and filters.q and filters.orden == "relevancia":
        fuzzy = await search_query.run_fuzzy(
            session,
            filters=filters,
            user_ctx=user_ctx,
            threshold=fuzzy_word_similarity_threshold,
        )
        if fuzzy.total > 0:
            result = fuzzy
            fuzzy_fallback = True
            logger.info("fuzzy_fallback_hit", extra={"q_len": len(filters.q)})

    unfiltered_total: int | None = None
    if _has_filter(filters):
        base = replace(
            filters,
            pagina=1,
            area_path=None,
            tipos=(),
            desde=None,
            hasta=None,
        )
        if fuzzy_fallback:
            unfiltered_total = await search_query.run_fuzzy_count(
                session,
                filters=base,
                user_ctx=user_ctx,
                threshold=fuzzy_word_similarity_threshold,
            )
        else:
            unfiltered_total = await search_query.run_count(
                session,
                filters=base,
                user_ctx=user_ctx,
                embedding=embedding,
                min_semantic_similarity=min_semantic_similarity,
            )

    return ExecuteResult(
        rows=result.rows,
        total=result.total,
        saturated=result.saturated,
        unfiltered_total=unfiltered_total,
        lexical_fallback=lexical_fallback,
        fuzzy_fallback=fuzzy_fallback,
    )
