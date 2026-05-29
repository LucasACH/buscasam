"""The report→queue→act→resolve→notify lifecycle (module map §core/moderation,
ADR-0010 §9). Sole writer of `documents.moderation_hidden_at`.

This slice (issue #76) lands only the Docente triage read; filing and the
hide/unhide/dismiss actions arrive in later slices.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class QueueEntry:
    doc_id: int
    title: str
    reasons: list[str]  # distinct reasons across open reports, sorted
    first_reported_at: datetime
    last_reported_at: datetime
    report_count: int


async def list_open_reports(session: AsyncSession) -> list[QueueEntry]:
    """One entry per document with at least one open report, ordered for triage
    (most-reported first, then most-recent activity). require_docente upstream.

    Resolved-only documents produce no row — the WHERE keeps only open reports.
    The unique partial index `(doc_id, reporter_user_id) WHERE status='open'`
    makes `count(*)` the distinct-reporter count.
    """
    rows = (
        await session.execute(
            text(
                "SELECT r.doc_id, d.titulo, "
                "       array_agg(DISTINCT r.reason ORDER BY r.reason) AS reasons, "
                "       min(r.created_at) AS first_reported_at, "
                "       max(r.created_at) AS last_reported_at, "
                "       count(*) AS report_count "
                "FROM document_reports r JOIN documents d ON d.id = r.doc_id "
                "WHERE r.status = 'open' "
                "GROUP BY r.doc_id, d.titulo "
                "ORDER BY report_count DESC, last_reported_at DESC, r.doc_id"
            )
        )
    ).mappings().all()
    return [
        QueueEntry(
            doc_id=r["doc_id"],
            title=r["titulo"],
            reasons=list(r["reasons"]),
            first_reported_at=r["first_reported_at"],
            last_reported_at=r["last_reported_at"],
            report_count=r["report_count"],
        )
        for r in rows
    ]
