"""Sole owner of search_events + search_clicks — relevance-eval instrumentation.

`record_search_event` logs one impression per relevance query ("what we
showed"); `record_click` attributes a result click back to it via the search_id
the result link carries. These feed the offline eval harness, never search
ranking — kept apart from document_reads (ADR-0014) on purpose.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.core.embed import normalize_query
from buscasam.core.search_query import Filters, ResultRow


async def record_search_event(
    session: AsyncSession,
    *,
    search_id: str,
    reader_key: str,
    filters: Filters,
    rows: list[ResultRow],
    total: int,
    saturated: bool,
    lexical_fallback: bool,
    fuzzy_fallback: bool,
    semantic_used: bool,
    latency_ms: int,
) -> None:
    """Persist one impression. Shares the request transaction; doc_ids is the
    ordered page shown so the harness can score rank-by-rank."""
    await session.execute(
        text(
            "INSERT INTO search_events ("
            "  search_id, reader_key, q, q_norm, orden, area_path, tipos, "
            "  desde, hasta, pagina, doc_ids, total, saturated, "
            "  lexical_fallback, fuzzy_fallback, semantic_used, latency_ms"
            ") VALUES ("
            "  :search_id, :reader_key, :q, :q_norm, :orden, :area_path, :tipos, "
            "  :desde, :hasta, :pagina, :doc_ids, :total, :saturated, "
            "  :lexical_fallback, :fuzzy_fallback, :semantic_used, :latency_ms"
            ")"
        ),
        {
            "search_id": search_id,
            "reader_key": reader_key,
            "q": filters.q,
            "q_norm": normalize_query(filters.q),
            "orden": filters.orden,
            "area_path": filters.area_path,
            "tipos": list(filters.tipos),
            "desde": filters.desde,
            "hasta": filters.hasta,
            "pagina": filters.pagina,
            "doc_ids": [r.doc_id for r in rows],
            "total": total,
            "saturated": saturated,
            "lexical_fallback": lexical_fallback,
            "fuzzy_fallback": fuzzy_fallback,
            "semantic_used": semantic_used,
            "latency_ms": latency_ms,
        },
    )


async def record_click(
    session: AsyncSession,
    *,
    search_id: str,
    doc_id: int,
    rank: int,
    reader_key: str,
) -> None:
    """Insert one attributed click, but only if `doc_id` was actually shown in
    that impression — the INSERT...SELECT is the membership gate: it matches a
    search_events row by search_id with doc_id in its doc_ids, so a forged or
    stale request (unknown search_id, or a doc never in the results) inserts
    nothing. Idempotent: a no-op on a repeat (search_id, doc_id)."""
    await session.execute(
        text(
            "INSERT INTO search_clicks (search_id, doc_id, rank, reader_key) "
            "SELECT :search_id, :doc_id, :rank, :reader_key "
            "FROM search_events "
            "WHERE search_id = :search_id AND :doc_id = ANY(doc_ids) "
            "ON CONFLICT DO NOTHING"
        ),
        {
            "search_id": search_id,
            "doc_id": doc_id,
            "rank": rank,
            "reader_key": reader_key,
        },
    )
