"""Readable headline-cosine retrieval — sole chokepoint (module map §core/related).

Owns five stacked invariants: source-after-access (security-load-bearing per
ADR-0010 §6, PRD story 33), headline-existence gate, candidate readable_where,
similarity floor (reused from search calibration; ADR-0002 §7), source exclusion.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.core.document_access import readable_where
from buscasam.core.documents import AuthorDisplay

if TYPE_CHECKING:
    from buscasam.core.auth import UserCtx


@dataclass(frozen=True)
class RelatedRow:
    doc_id: int
    titulo: str
    autores: list[AuthorDisplay]
    area_path: str
    tipo: str
    fecha: date | None
    similarity: float


async def fetch_related(
    session: AsyncSession,
    doc_id: int,
    user_ctx: "UserCtx",
    *,
    k: int = 5,
    min_semantic_similarity: float,
) -> list[RelatedRow] | None:
    """Return up to `k` related rows, or `None` when source is unreadable.

    Source-access check is the *first* SQL: the source headline embedding is
    loaded only after the source passes `readable_where(user_ctx)` (ADR-0010 §6,
    PRD story 33). `None` is the same 404 signal `get_detail` uses; `[]` means
    the source is readable but has no `is_headline AND is_current` chunk
    (candidate-only state, mid-flight headline reindex, or pre-headline docs).
    """
    src_where, src_params = readable_where("d", user_ctx)
    readable = (
        await session.execute(
            text(
                f"SELECT 1 FROM documents d WHERE d.id = :doc_id AND ({src_where})"
            ),
            {"doc_id": doc_id, **src_params},
        )
    ).scalar_one_or_none()
    if readable is None:
        return None

    # Source readable: now (and only now) load the source headline embedding.
    # When the source has no `is_headline AND is_current` chunk the WITH src
    # CTE is empty, the cosine WHERE rejects every candidate, and we return [].
    cand_where, cand_params = readable_where("d", user_ctx)
    rows = (
        await session.execute(
            text(
                "WITH src AS ("
                "  SELECT embedding FROM chunks "
                "  WHERE doc_id = :doc_id AND is_headline AND is_current "
                "  LIMIT 1"
                ") "
                "SELECT d.id, d.titulo, d.fecha, d.area_path::text AS area_path, "
                "       d.tipo, "
                "       1 - (c.embedding <=> (SELECT embedding FROM src)) "
                "         AS similarity "
                "FROM chunks c "
                "JOIN documents d ON d.id = c.doc_id "
                f"WHERE c.is_headline AND c.is_current "
                f"  AND d.id <> :doc_id "
                f"  AND ({cand_where}) "
                f"  AND 1 - (c.embedding <=> (SELECT embedding FROM src)) "
                f"      >= :min_sim "
                "ORDER BY similarity DESC, d.id "
                "LIMIT :k"
            ),
            {
                "doc_id": doc_id,
                "min_sim": min_semantic_similarity,
                "k": k,
                **cand_params,
            },
        )
    ).mappings().all()
    if not rows:
        return []

    survivor_ids = [r["id"] for r in rows]
    author_rows = (
        await session.execute(
            text(
                "SELECT doc_id, display_name, user_id "
                "FROM document_authors WHERE doc_id = ANY(:ids) ORDER BY doc_id, id"
            ),
            {"ids": survivor_ids},
        )
    ).mappings().all()
    by_doc: dict[int, list[AuthorDisplay]] = {sid: [] for sid in survivor_ids}
    for a in author_rows:
        by_doc[a["doc_id"]].append(
            AuthorDisplay(display_name=a["display_name"], user_id=a["user_id"])
        )

    return [
        RelatedRow(
            doc_id=r["id"],
            titulo=r["titulo"],
            autores=by_doc[r["id"]],
            area_path=r["area_path"],
            tipo=r["tipo"],
            fecha=r["fecha"],
            similarity=float(r["similarity"]),
        )
        for r in rows
    ]
