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
from buscasam.core.search_query import HNSW_EF_SEARCH

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
    # No `is_headline AND is_current` chunk → the headline-existence gate returns
    # `[]` (candidate-only state, mid-flight headline reindex, or pre-headline doc).
    src_vec = (
        await session.execute(
            text(
                "SELECT embedding::text FROM chunks "
                "WHERE doc_id = :doc_id AND is_headline AND is_current LIMIT 1"
            ),
            {"doc_id": doc_id},
        )
    ).scalar_one_or_none()
    if src_vec is None:
        return []

    # Order by raw cosine distance ascending so pgvector's HNSW index
    # (chunks_embedding_hnsw, halfvec_cosine_ops) drives the scan; `1 - distance`
    # is computed only for the SELECT list and the min_sim floor. readable_where +
    # is_headline + is_current + min_sim are post-filters, so widen the candidate
    # set like _run_hybrid (strict_order + ef_search) to avoid undercounting.
    await session.execute(text("SET LOCAL hnsw.iterative_scan = 'strict_order'"))
    await session.execute(text(f"SET LOCAL hnsw.ef_search = {HNSW_EF_SEARCH}"))

    # The `cand` CTE orders by raw distance alone so the HNSW index drives it;
    # the `d.id` tie-break moves to the outer SELECT (an incremental sort over the
    # ≤k survivors), since a secondary ORDER BY key inside the CTE would forbid the
    # index — mirrors _run_hybrid's distance-only `sem` candidate ordering.
    cand_where, cand_params = readable_where("d", user_ctx)
    rows = (
        await session.execute(
            text(
                "WITH cand AS ("
                "  SELECT d.id, d.titulo, d.fecha, d.area_path::text AS area_path, "
                "         d.tipo, "
                "         c.embedding <=> CAST(:src_vec AS halfvec(1024)) AS distance "
                "  FROM chunks c "
                "  JOIN documents d ON d.id = c.doc_id "
                f"  WHERE c.is_headline AND c.is_current "
                f"    AND d.id <> :doc_id "
                f"    AND ({cand_where}) "
                f"    AND 1 - (c.embedding <=> CAST(:src_vec AS halfvec(1024))) "
                f"        >= :min_sim "
                "  ORDER BY c.embedding <=> CAST(:src_vec AS halfvec(1024)) "
                "  LIMIT :k"
                ") "
                "SELECT id, titulo, fecha, area_path, tipo, "
                "       1 - distance AS similarity "
                "FROM cand "
                "ORDER BY distance, id"
            ),
            {
                "doc_id": doc_id,
                "src_vec": src_vec,
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
