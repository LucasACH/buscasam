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
class ActionOutcome:
    action_id: int


async def hide(
    session: AsyncSession, docente_ctx: UserCtx, report_id: int, reason: Reason
) -> ActionOutcome | None:
    """Stamp `documents.moderation_hidden_at`, append a `hide` audit row, and
    resolve all open reports on the document — in one transaction. Returns None
    when the report is unknown or its document is author-soft-deleted (router →
    404). Touches no other `documents` column (stories 24-25)."""
    doc_id = await _resolve_case(session, report_id)
    if doc_id is None:
        return None
    action_id = await _append_action(session, report_id, docente_ctx, "hide", reason)
    await _resolve_open_reports(session, doc_id)
    await session.execute(
        text("UPDATE documents SET moderation_hidden_at = now() WHERE id = :d"),
        {"d": doc_id},
    )
    await _notify_authors(session, doc_id, action_id, "document_hidden", reason)
    return ActionOutcome(action_id=action_id)


async def unhide(
    session: AsyncSession,
    docente_ctx: UserCtx,
    report_id: int,
    reason: Reason | None = None,
) -> ActionOutcome | None:
    """Clear `documents.moderation_hidden_at` unconditionally, append an
    `unhide` audit row, and resolve all open reports — one transaction. Re-hide/
    re-unhide leaves no residue beyond the log (story 33). None on unknown report
    or author-soft-deleted doc."""
    doc_id = await _resolve_case(session, report_id)
    if doc_id is None:
        return None
    action_id = await _append_action(session, report_id, docente_ctx, "unhide", reason)
    await _resolve_open_reports(session, doc_id)
    await session.execute(
        text("UPDATE documents SET moderation_hidden_at = NULL WHERE id = :d"),
        {"d": doc_id},
    )
    await _notify_authors(session, doc_id, action_id, "document_unhidden", reason)
    return ActionOutcome(action_id=action_id)


async def dismiss(
    session: AsyncSession,
    docente_ctx: UserCtx,
    report_id: int,
    reason: Reason | None = None,
) -> ActionOutcome | None:
    """Append a `dismiss` audit row and resolve all open reports — the matter is
    settled for the document (story 23). Touches no `documents` column and
    notifies no one (story 28). None on unknown report or author-soft-deleted
    doc."""
    doc_id = await _resolve_case(session, report_id)
    if doc_id is None:
        return None
    action_id = await _append_action(session, report_id, docente_ctx, "dismiss", reason)
    await _resolve_open_reports(session, doc_id)
    return ActionOutcome(action_id=action_id)


async def _resolve_case(session: AsyncSession, report_id: int) -> int | None:
    """The report's document, excluding author-soft-deleted (story 18)."""
    return (
        await session.execute(
            text(
                "SELECT d.id FROM document_reports r JOIN documents d ON d.id = r.doc_id "
                "WHERE r.id = :r AND d.soft_deleted_at IS NULL"
            ),
            {"r": report_id},
        )
    ).scalar_one_or_none()


async def _append_action(
    session: AsyncSession,
    report_id: int,
    docente_ctx: UserCtx,
    action: str,
    reason: str | None,
) -> int:
    return (
        await session.execute(
            text(
                "INSERT INTO moderation_actions "
                "(report_id, docente_user_id, action, reason) "
                "VALUES (:r, :u, :a, :reason) RETURNING id"
            ),
            {"r": report_id, "u": docente_ctx.user_id, "a": action, "reason": reason},
        )
    ).scalar_one()


async def _notify_authors(
    session: AsyncSession,
    doc_id: int,
    action_id: int,
    kind: str,
    reason: str | None,
) -> None:
    """One in-app notification per registered author (owner + accepted,
    `user_id NOT NULL`); external authors are skipped. `event_key` is keyed per
    `moderation_actions` id, so a retry of the same action never double-notifies
    (story 29)."""
    await session.execute(
        text(
            "INSERT INTO notifications (user_id, event_key, kind, payload_json) "
            "SELECT da.user_id, :ek, :kind, "
            "       jsonb_build_object('doc_id', cast(:doc_id as bigint), "
            "                          'doc_title', d.titulo, "
            "                          'reason', cast(:reason as text)) "
            "FROM document_authors da JOIN documents d ON d.id = da.doc_id "
            "WHERE da.doc_id = :doc_id AND da.status IN ('owner', 'accepted') "
            "  AND da.user_id IS NOT NULL "
            "ON CONFLICT (user_id, event_key) DO NOTHING"
        ),
        {"ek": f"{kind}:{action_id}", "kind": kind, "doc_id": doc_id, "reason": reason},
    )


async def _resolve_open_reports(session: AsyncSession, doc_id: int) -> None:
    await session.execute(
        text(
            "UPDATE document_reports SET status = 'resolved' "
            "WHERE doc_id = :d AND status = 'open'"
        ),
        {"d": doc_id},
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
