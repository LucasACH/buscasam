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


async def run(
    session: AsyncSession,
    *,
    filters: Filters,
    user_ctx: UserCtx,
    embedding: object | None = None,
) -> Results:
    where = invitado_where("d")
    offset = (filters.pagina - 1) * PAGE_SIZE
    sql = text(
        f"""
        WITH ranked AS (
            SELECT
                c.doc_id,
                c.body_text,
                ts_rank_cd(c.body_tsv, plainto_tsquery('es_unaccent', :q)) AS score,
                ROW_NUMBER() OVER (
                    PARTITION BY c.doc_id
                    ORDER BY ts_rank_cd(c.body_tsv, plainto_tsquery('es_unaccent', :q)) DESC
                ) AS rn
            FROM chunks c
            JOIN documents d ON d.id = c.doc_id
            WHERE c.body_tsv @@ plainto_tsquery('es_unaccent', :q)
              AND {where}
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
    rows = (
        await session.execute(
            sql,
            {
                "q": filters.q,
                "cap": RELEVANCE_CAP,
                "headline_opts": TS_HEADLINE_OPTS,
                "limit": PAGE_SIZE,
                "offset": offset,
            },
        )
    ).all()

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
    )
