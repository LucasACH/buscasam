"""Lexical retrieval chokepoint for the invitado branch (ADR-0003 §3, ADR-0001 §2-3).

Slice 2 ships the lexical-only path: hybrid RRF and the semantic CTE arrive
when the embedding seam lands. Predicate stays inside this module per the
search-mvp module map.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.core.document_access import invitado_where

PAGE_SIZE = 10
RELEVANCE_CAP = 200
TS_HEADLINE_OPTS = "StartSel=<mark>, StopSel=</mark>, MaxFragments=1, MaxWords=20, MinWords=5"


@dataclass(frozen=True)
class Filters:
    q: str
    pagina: int = 1
    area_path: str | None = None


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


async def run(
    session: AsyncSession,
    *,
    filters: Filters,
    user_ctx: UserCtx,
) -> Results:
    where = invitado_where("d")
    area_clause = "AND d.area_path <@ CAST(:area AS ltree)" if filters.area_path else ""
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
    params = {
        "q": filters.q,
        "cap": RELEVANCE_CAP,
        "headline_opts": TS_HEADLINE_OPTS,
        "limit": PAGE_SIZE,
        "offset": offset,
    }
    if filters.area_path:
        params["area"] = filters.area_path
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
