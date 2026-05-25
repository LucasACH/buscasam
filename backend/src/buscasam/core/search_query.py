"""Hybrid retrieval chokepoint for the invitado branch (ADR-0001, ADR-0003 §3).

Slice 2 shipped the lexical-only path. Slice 5 layers RRF-fused semantic
retrieval on top — `embedding=None` keeps the lexical-only pipeline byte-for-
byte unchanged. Predicate stays inside this module per the search-mvp module
map.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.core.document_access import invitado_where

PAGE_SIZE = 10
RELEVANCE_CAP = 200
RRF_K = 60
HNSW_EF_SEARCH = 40
TS_HEADLINE_OPTS = "StartSel=<mark>, StopSel=</mark>, MaxFragments=1, MaxWords=20, MinWords=5"


@dataclass(frozen=True)
class Filters:
    q: str
    pagina: int = 1
    area_path: str | None = None
    tipos: tuple[str, ...] = ()
    desde: int | None = None
    hasta: int | None = None


@dataclass(frozen=True)
class UserCtx:
    role: str


@dataclass(frozen=True)
class ResultRow:
    doc_id: int
    titulo: str
    fecha: date
    area_path: str
    tipo: str
    abstract: str | None
    snippet: str


@dataclass(frozen=True)
class Results:
    rows: list[ResultRow]
    total: int
    saturated: bool


def _filter_clauses(filters: Filters) -> tuple[str, str, str, str]:
    return (
        "AND d.area_path <@ CAST(:area AS ltree)" if filters.area_path is not None else "",
        "AND d.tipo = ANY(:tipos)" if filters.tipos else "",
        "AND EXTRACT(year FROM d.fecha) >= :desde" if filters.desde is not None else "",
        "AND EXTRACT(year FROM d.fecha) <= :hasta" if filters.hasta is not None else "",
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
    if embedding is None:
        return await _run_lexical(session, filters)
    return await _run_hybrid(session, filters, embedding, min_semantic_similarity)


async def _run_lexical(session: AsyncSession, filters: Filters) -> Results:
    where = invitado_where("d")
    area_clause, tipo_clause, desde_clause, hasta_clause = _filter_clauses(filters)
    offset = (filters.pagina - 1) * PAGE_SIZE
    sql = text(
        f"""
        WITH scored AS (
            SELECT
                c.doc_id,
                c.body_text,
                ts_rank_cd(c.body_tsv, plainto_tsquery('es_unaccent', :q)) AS score
            FROM chunks c
            JOIN documents d ON d.id = c.doc_id
            WHERE c.body_tsv @@ plainto_tsquery('es_unaccent', :q)
              AND {where}
              {area_clause}
              {tipo_clause}
              {desde_clause}
              {hasta_clause}
        ),
        ranked AS (
            SELECT
                doc_id,
                body_text,
                score,
                ROW_NUMBER() OVER (
                    PARTITION BY doc_id
                    ORDER BY score DESC
                ) AS rn
            FROM scored
        ),
        best_per_doc AS (
            SELECT doc_id, body_text, score FROM ranked WHERE rn = 1
        ),
        capped AS (
            SELECT doc_id, body_text, score
            FROM best_per_doc
            ORDER BY score DESC
            LIMIT :cap
        )
        SELECT
            d.id           AS doc_id,
            d.titulo       AS titulo,
            d.fecha        AS fecha,
            d.area_path::text AS area_path,
            d.tipo         AS tipo,
            d.abstract     AS abstract,
            ts_headline(
                'es_unaccent',
                c.body_text,
                plainto_tsquery('es_unaccent', :q),
                :headline_opts
            ) AS snippet,
            (SELECT count(*) FROM capped) AS total
        FROM capped c
        JOIN documents d ON d.id = c.doc_id
        ORDER BY c.score DESC
        LIMIT :limit OFFSET :offset
        """
    )
    params: dict[str, object] = {
        "q": filters.q,
        "cap": RELEVANCE_CAP,
        "headline_opts": TS_HEADLINE_OPTS,
        "limit": PAGE_SIZE,
        "offset": offset,
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
            )
            for r in rows
        ],
        total=total,
        saturated=total >= RELEVANCE_CAP,
    )


async def _run_hybrid(
    session: AsyncSession,
    filters: Filters,
    embedding: np.ndarray,
    min_semantic_similarity: float,
) -> Results:
    await session.execute(text("SET LOCAL hnsw.iterative_scan = 'strict_order'"))
    await session.execute(text(f"SET LOCAL hnsw.ef_search = {HNSW_EF_SEARCH}"))

    where = invitado_where("d")
    area_clause, tipo_clause, desde_clause, hasta_clause = _filter_clauses(filters)
    offset = (filters.pagina - 1) * PAGE_SIZE
    sql = text(
        f"""
        WITH lex AS (
            SELECT
                c.doc_id,
                c.body_text,
                ts_rank_cd(c.body_tsv, plainto_tsquery('es_unaccent', :q)) AS score
            FROM chunks c
            JOIN documents d ON d.id = c.doc_id
            WHERE c.body_tsv @@ plainto_tsquery('es_unaccent', :q)
              AND {where}
              {area_clause}
              {tipo_clause}
              {desde_clause}
              {hasta_clause}
        ),
        lex_best AS (
            SELECT DISTINCT ON (doc_id) doc_id, body_text, score
            FROM lex
            ORDER BY doc_id, score DESC
        ),
        lex_ranked AS (
            SELECT doc_id, body_text, score,
                   ROW_NUMBER() OVER (ORDER BY score DESC) AS rank
            FROM lex_best
            LIMIT :cap
        ),
        sem AS (
            SELECT
                c.doc_id,
                1 - (c.embedding <=> CAST(:embedding AS halfvec(1024))) AS similarity
            FROM chunks c
            JOIN documents d ON d.id = c.doc_id
            WHERE {where}
              {area_clause}
              {tipo_clause}
              {desde_clause}
              {hasta_clause}
            ORDER BY c.embedding <=> CAST(:embedding AS halfvec(1024))
            LIMIT :cap
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
            CASE
                WHEN c.body_text IS NOT NULL THEN
                    ts_headline(
                        'es_unaccent',
                        c.body_text,
                        plainto_tsquery('es_unaccent', :q),
                        :headline_opts
                    )
                ELSE LEFT(COALESCE(d.abstract, ''), 200)
            END AS snippet,
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
        "headline_opts": TS_HEADLINE_OPTS,
        "limit": PAGE_SIZE,
        "offset": offset,
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
            )
            for r in rows
        ],
        total=total,
        saturated=total >= RELEVANCE_CAP,
    )
