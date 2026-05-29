"""The report→queue→act→resolve→notify lifecycle and owner of the two
moderation tables (module map §core/moderation, ADR-0010 §9)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.core.document_access import readable_where

if TYPE_CHECKING:
    from buscasam.core.auth import UserCtx

Reason = Literal["spam", "contenido_inadecuado", "plagio", "error"]


class DocumentNotReadable(Exception):
    """The reporter cannot read the target document — the router maps this to a
    uniform 404 so hidden/private/deleted existence never leaks."""


async def file_report(
    session: AsyncSession, user_ctx: UserCtx, doc_id: int, reason: Reason
) -> None:
    """Insert an `open` report, gated by `readable_where` (ADR-0010 §7).

    A second open report by the same reporter on the same doc is a harmless
    no-op (`ON CONFLICT` on the unique partial index
    `(doc_id, reporter_user_id) WHERE status='open'`). A non-readable doc raises
    `DocumentNotReadable` — `require_authenticated` is the caller's job."""
    where, params = readable_where("d", user_ctx)
    readable = (
        await session.execute(
            text(f"SELECT 1 FROM documents d WHERE d.id = :doc_id AND ({where})"),
            {"doc_id": doc_id, **params},
        )
    ).scalar_one_or_none()
    if readable is None:
        raise DocumentNotReadable

    await session.execute(
        text(
            "INSERT INTO document_reports (doc_id, reporter_user_id, reason) "
            "VALUES (:doc_id, :reporter_user_id, :reason) "
            "ON CONFLICT (doc_id, reporter_user_id) WHERE status = 'open' "
            "DO NOTHING"
        ),
        {"doc_id": doc_id, "reporter_user_id": user_ctx.user_id, "reason": reason},
    )


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
