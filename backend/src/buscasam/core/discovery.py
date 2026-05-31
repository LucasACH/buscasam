"""Sole owner of document_reads — read tracking + más leídos (module map
§core/discovery, ADR-0014).

`record_read` is the only writer; `most_read` is the only reader. Reads never
feed search ranking (ADR-0014).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.core.document_access import invitado_where


@dataclass(frozen=True)
class MostReadRow:
    doc_id: int
    titulo: str
    area_path: str
    tipo: str
    fecha: date | None
    reads: int


async def record_read(session: AsyncSession, doc_id: int, reader_key: str) -> None:
    """Idempotent insert of one lectura; no-op on conflict, never raises on a
    duplicate. Records for any opened document regardless of visibility — the
    público filter is a read-time concern of `most_read`."""
    await session.execute(
        text(
            "INSERT INTO document_reads (doc_id, reader_key, read_day) "
            "VALUES (:doc_id, :reader_key, CURRENT_DATE) "
            "ON CONFLICT DO NOTHING"
        ),
        {"doc_id": doc_id, "reader_key": reader_key},
    )


async def most_read(
    session: AsyncSession, *, window_days: int, limit: int
) -> list[MostReadRow]:
    """The más leídos ranking: público documents ordered by distinct lectura
    count within the rolling `window_days`, capped at `limit`. One shared
    ranking — takes no UserCtx (público-only, ADR-0014)."""
    rows = (
        await session.execute(
            text(
                "SELECT d.id AS doc_id, d.titulo, d.area_path, d.tipo, d.fecha, "
                "       count(*) AS reads "
                "FROM documents d "
                "JOIN document_reads r ON r.doc_id = d.id "
                f"WHERE {invitado_where('d')} "
                "  AND r.read_day > CURRENT_DATE - :window_days "
                "GROUP BY d.id "
                "ORDER BY reads DESC, d.id "
                "LIMIT :limit"
            ),
            {"window_days": window_days, "limit": limit},
        )
    ).all()
    return [
        MostReadRow(
            doc_id=r.doc_id,
            titulo=r.titulo,
            area_path=r.area_path,
            tipo=r.tipo,
            fecha=r.fecha,
            reads=r.reads,
        )
        for r in rows
    ]
