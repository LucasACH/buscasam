"""Hybrid retrieval chokepoint for the invitado branch (ADR-0001, ADR-0003 §3).

Slice 2 shipped the lexical-only path. Slice 5 layers RRF-fused semantic
retrieval on top — `embedding=None` keeps the lexical-only pipeline byte-for-
byte unchanged. Predicate stays inside this module per the search-mvp module
map.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Literal

import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.core.document_access import readable_where

if TYPE_CHECKING:
    from buscasam.core.auth import UserCtx

Orden = Literal["relevancia", "recientes"]

PAGE_SIZE = 10
RELEVANCE_CAP = 200
RRF_K = 60
HNSW_EF_SEARCH = 40
# Chunks per doc are bounded but >1; over-fetch the semantic CTE so the
# MAX-per-doc dedup still surfaces ~RELEVANCE_CAP distinct docs before fusion.
SEMANTIC_CHUNK_OVERFETCH = 5
TS_HEADLINE_OPTS = "StartSel=<mark>, StopSel=</mark>, MaxFragments=1, MaxWords=20, MinWords=5"


@dataclass(frozen=True)
class Filters:
    q: str
    pagina: int = 1
    area_path: str | None = None
    tipos: tuple[str, ...] = ()
    desde: int | None = None
    hasta: int | None = None
    orden: Orden = "relevancia"


@dataclass(frozen=True)
class ResultRow:
    doc_id: int
    titulo: str
    fecha: date
    area_path: str
    tipo: str
    abstract: str | None
    snippet: str
    snippet_is_html: bool
    visibility: str


@dataclass(frozen=True)
class Results:
    rows: list[ResultRow]
    total: int
    saturated: bool


def _filter_clauses(filters: Filters) -> str:
    return "\n              ".join(
        clause
        for clause in (
            "AND d.area_path <@ CAST(:area AS ltree)" if filters.area_path is not None else None,
            "AND d.tipo = ANY(:tipos)" if filters.tipos else None,
            "AND EXTRACT(year FROM d.fecha) >= :desde" if filters.desde is not None else None,
            "AND EXTRACT(year FROM d.fecha) <= :hasta" if filters.hasta is not None else None,
        )
        if clause is not None
    )


def _lexical_candidates_ctes(
    *,
    where: str,
    filter_clauses: str,
    cap: int | None,
) -> tuple[str, dict[str, object]]:
    """CTEs exposing `lex_best (doc_id, body_text, score)` and `lex_ranked (+ rank)`,
    the best-matching chunk per readable doc.

    Embed as `WITH {ctes}, mine AS (...) SELECT ...`. Caller must bind `:q`; when
    `cap` is not None, the returned params dict adds `:lex_cap`.
    """
    cap_clause = "ORDER BY score DESC LIMIT :lex_cap" if cap is not None else ""
    ctes = f"""
        lex_scored AS (
            SELECT c.doc_id,
                   c.body_text,
                   ts_rank_cd(c.body_tsv, plainto_tsquery('es_unaccent', :q)) AS score
            FROM chunks c
            JOIN documents d ON d.id = c.doc_id
            WHERE c.body_tsv @@ plainto_tsquery('es_unaccent', :q)
              AND c.is_current
              AND {where}
              {filter_clauses}
        ),
        lex_best AS (
            SELECT doc_id, body_text, score
            FROM (
                SELECT doc_id, body_text, score,
                       ROW_NUMBER() OVER (PARTITION BY doc_id ORDER BY score DESC) AS rn
                FROM lex_scored
            ) s
            WHERE rn = 1
        ),
        lex_ranked AS (
            SELECT doc_id, body_text, score,
                   ROW_NUMBER() OVER (ORDER BY score DESC) AS rank
            FROM lex_best
            {cap_clause}
        )
    """
    params: dict[str, object] = {}
    if cap is not None:
        params["lex_cap"] = cap
    return ctes, params


def _headline_expr(body_col: str) -> str:
    """ts_headline SQL expression; caller must bind `:q` and `:headline_opts`."""
    return (
        f"ts_headline('es_unaccent', {body_col}, "
        f"plainto_tsquery('es_unaccent', :q), :headline_opts)"
    )


def _filter_params(filters: Filters) -> dict[str, object]:
    params: dict[str, object] = {}
    if filters.area_path is not None:
        params["area"] = filters.area_path
    if filters.tipos:
        params["tipos"] = list(filters.tipos)
    if filters.desde is not None:
        params["desde"] = filters.desde
    if filters.hasta is not None:
        params["hasta"] = filters.hasta
    return params


def _halfvec_literal(embedding: np.ndarray) -> str:
    return "[" + ",".join(f"{float(v):.6f}" for v in embedding) + "]"


async def run(
    session: AsyncSession,
    *,
    filters: Filters,
    user_ctx: UserCtx,
    embedding: np.ndarray | None = None,
    min_semantic_similarity: float = 0.78,
) -> Results:
    if filters.orden == "recientes":
        return await _run_recientes(session, filters, user_ctx)
    if embedding is None:
        return await _run_lexical(session, filters, user_ctx)
    return await _run_hybrid(
        session, filters, user_ctx, embedding, min_semantic_similarity
    )


async def _run_recientes(
    session: AsyncSession, filters: Filters, user_ctx: UserCtx
) -> Results:
    where, where_params = readable_where("d", user_ctx)
    filter_clauses = _filter_clauses(filters)
    params: dict[str, object] = {**_filter_params(filters), **where_params}
    params["limit"] = PAGE_SIZE
    params["offset"] = (filters.pagina - 1) * PAGE_SIZE

    if filters.q:
        lex_ctes, lex_params = _lexical_candidates_ctes(
            where=where, filter_clauses=filter_clauses, cap=None
        )
        params["q"] = filters.q
        params["headline_opts"] = TS_HEADLINE_OPTS
        params.update(lex_params)
        sql = text(
            f"""
            WITH {lex_ctes}
            SELECT
                d.id, d.titulo, d.fecha, d.area_path::text AS area_path,
                d.tipo, d.abstract, d.visibility,
                {_headline_expr("lex.body_text")} AS snippet,
                (SELECT count(*) FROM lex_best) AS total
            FROM lex_best lex
            JOIN documents d ON d.id = lex.doc_id
            ORDER BY d.fecha DESC, d.id DESC
            LIMIT :limit OFFSET :offset
            """
        )
    else:
        sql = text(
            f"""
            SELECT
                d.id, d.titulo, d.fecha, d.area_path::text AS area_path,
                d.tipo, d.abstract, d.visibility,
                LEFT(COALESCE(d.abstract, ''), 200) AS snippet,
                count(*) OVER () AS total
            FROM documents d
            WHERE {where}
              {filter_clauses}
            ORDER BY d.fecha DESC, d.id DESC
            LIMIT :limit OFFSET :offset
            """
        )

    rows = (await session.execute(sql, params)).all()
    total = rows[0].total if rows else 0
    snippet_is_html = bool(filters.q)
    return Results(
        rows=[
            ResultRow(
                doc_id=r.id,
                titulo=r.titulo,
                fecha=r.fecha,
                area_path=r.area_path,
                tipo=r.tipo,
                abstract=r.abstract,
                snippet=r.snippet,
                snippet_is_html=snippet_is_html,
                visibility=r.visibility,
            )
            for r in rows
        ],
        total=total,
        saturated=False,
    )


async def _run_lexical(
    session: AsyncSession, filters: Filters, user_ctx: UserCtx
) -> Results:
    where, where_params = readable_where("d", user_ctx)
    filter_clauses = _filter_clauses(filters)
    lex_ctes, lex_params = _lexical_candidates_ctes(
        where=where, filter_clauses=filter_clauses, cap=RELEVANCE_CAP
    )
    offset = (filters.pagina - 1) * PAGE_SIZE
    sql = text(
        f"""
        WITH {lex_ctes}
        SELECT
            d.id           AS doc_id,
            d.titulo       AS titulo,
            d.fecha        AS fecha,
            d.area_path::text AS area_path,
            d.tipo         AS tipo,
            d.abstract     AS abstract,
            d.visibility   AS visibility,
            {_headline_expr("lex.body_text")} AS snippet,
            (SELECT count(*) FROM lex_ranked) AS total
        FROM lex_ranked lex
        JOIN documents d ON d.id = lex.doc_id
        ORDER BY lex.rank
        LIMIT :limit OFFSET :offset
        """
    )
    params: dict[str, object] = {
        "q": filters.q,
        "headline_opts": TS_HEADLINE_OPTS,
        "limit": PAGE_SIZE,
        "offset": offset,
        **lex_params,
        **where_params,
        **_filter_params(filters),
    }
    rows = (await session.execute(sql, params)).all()
    total = rows[0].total if rows else 0
    return Results(
        rows=[
            ResultRow(
                doc_id=r.doc_id,
                titulo=r.titulo,
                fecha=r.fecha,
                area_path=r.area_path,
                tipo=r.tipo,
                abstract=r.abstract,
                snippet=r.snippet,
                snippet_is_html=True,
                visibility=r.visibility,
            )
            for r in rows
        ],
        total=total,
        saturated=total >= RELEVANCE_CAP,
    )


async def _run_hybrid(
    session: AsyncSession,
    filters: Filters,
    user_ctx: UserCtx,
    embedding: np.ndarray,
    min_semantic_similarity: float,
) -> Results:
    await session.execute(text("SET LOCAL hnsw.iterative_scan = 'strict_order'"))
    await session.execute(text(f"SET LOCAL hnsw.ef_search = {HNSW_EF_SEARCH}"))

    where, where_params = readable_where("d", user_ctx)
    filter_clauses = _filter_clauses(filters)
    lex_ctes, lex_params = _lexical_candidates_ctes(
        where=where, filter_clauses=filter_clauses, cap=RELEVANCE_CAP
    )
    offset = (filters.pagina - 1) * PAGE_SIZE
    sql = text(
        f"""
        WITH {lex_ctes},
        sem AS (
            SELECT
                c.doc_id,
                1 - (c.embedding <=> CAST(:embedding AS halfvec(1024))) AS similarity
            FROM chunks c
            JOIN documents d ON d.id = c.doc_id
            WHERE c.is_current
              AND {where}
              {filter_clauses}
            ORDER BY c.embedding <=> CAST(:embedding AS halfvec(1024))
            LIMIT :sem_chunk_cap
        ),
        sem_best AS (
            SELECT doc_id, MAX(similarity) AS similarity
            FROM sem
            GROUP BY doc_id
        ),
        sem_ranked AS (
            SELECT doc_id, similarity,
                   ROW_NUMBER() OVER (ORDER BY similarity DESC) AS rank
            FROM sem_best
            LIMIT :cap
        ),
        fused AS (
            SELECT
                COALESCE(l.doc_id, s.doc_id) AS doc_id,
                l.body_text                   AS body_text,
                l.score                       AS lex_score,
                s.similarity                  AS sem_sim,
                COALESCE(1.0 / (:rrf_k + l.rank), 0)
                  + COALESCE(1.0 / (:rrf_k + s.rank), 0) AS rrf
            FROM lex_ranked l
            FULL OUTER JOIN sem_ranked s USING (doc_id)
        ),
        filtered AS (
            SELECT *
            FROM fused
            WHERE lex_score IS NOT NULL
               OR sem_sim >= :min_sim
        ),
        capped AS (
            SELECT *
            FROM filtered
            ORDER BY rrf DESC
            LIMIT :cap
        )
        SELECT
            d.id              AS doc_id,
            d.titulo          AS titulo,
            d.fecha           AS fecha,
            d.area_path::text AS area_path,
            d.tipo            AS tipo,
            d.abstract        AS abstract,
            d.visibility      AS visibility,
            CASE
                WHEN c.body_text IS NOT NULL THEN {_headline_expr("c.body_text")}
                ELSE LEFT(COALESCE(d.abstract, ''), 200)
            END AS snippet,
            (c.body_text IS NOT NULL) AS snippet_is_html,
            (SELECT count(*) FROM capped) AS total
        FROM capped c
        JOIN documents d ON d.id = c.doc_id
        ORDER BY c.rrf DESC
        LIMIT :limit OFFSET :offset
        """
    )
    params: dict[str, object] = {
        "q": filters.q,
        "embedding": _halfvec_literal(embedding),
        "min_sim": min_semantic_similarity,
        "rrf_k": RRF_K,
        "cap": RELEVANCE_CAP,
        "sem_chunk_cap": RELEVANCE_CAP * SEMANTIC_CHUNK_OVERFETCH,
        "headline_opts": TS_HEADLINE_OPTS,
        "limit": PAGE_SIZE,
        "offset": offset,
        **lex_params,
        **where_params,
        **_filter_params(filters),
    }
    rows = (await session.execute(sql, params)).all()
    total = rows[0].total if rows else 0
    return Results(
        rows=[
            ResultRow(
                doc_id=r.doc_id,
                titulo=r.titulo,
                fecha=r.fecha,
                area_path=r.area_path,
                tipo=r.tipo,
                abstract=r.abstract,
                snippet=r.snippet,
                snippet_is_html=r.snippet_is_html,
                visibility=r.visibility,
            )
            for r in rows
        ],
        total=total,
        saturated=total >= RELEVANCE_CAP,
    )
