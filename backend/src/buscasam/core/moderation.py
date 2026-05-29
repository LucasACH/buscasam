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
    report_id: int  # a representative open report, for report-scoped inspect/action
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
                "SELECT r.doc_id, max(r.id) AS report_id, d.titulo, "
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
            report_id=r["report_id"],
            title=r["titulo"],
            reasons=list(r["reasons"]),
            first_reported_at=r["first_reported_at"],
            last_reported_at=r["last_reported_at"],
            report_count=r["report_count"],
        )
        for r in rows
    ]


@dataclass(frozen=True)
class ActionOutcome:
    action_id: int
    doc_id: int


# hide/unhide notify registered authors; dismiss notifies no one. The event_key
# format `{kind}:{action_id}` is owned here (the single producer).
_NOTIFY_KIND = {"hide": "document_hidden", "unhide": "document_unhidden"}


async def hide(
    session: AsyncSession, docente_ctx: UserCtx, report_id: int, reason: Reason
) -> ActionOutcome | None:
    """Stamp `documents.moderation_hidden_at`, append a `hide` action, resolve
    all open reports on the doc, and notify every registered author — one
    transaction. None when the report is unknown or its doc is author-soft-
    deleted (router → 404). require_docente upstream."""
    return await _act(session, docente_ctx, report_id, "hide", reason)


async def unhide(
    session: AsyncSession, docente_ctx: UserCtx, report_id: int, reason: Reason | None = None
) -> ActionOutcome | None:
    """Clear `moderation_hidden_at`, append an `unhide` action, resolve all open
    reports, and notify every registered author — one transaction. None on an
    unknown/author-soft-deleted case."""
    return await _act(session, docente_ctx, report_id, "unhide", reason)


async def dismiss(
    session: AsyncSession, docente_ctx: UserCtx, report_id: int, reason: Reason | None = None
) -> ActionOutcome | None:
    """Append a `dismiss` action and resolve all open reports — the matter is
    settled for the document — without touching `moderation_hidden_at` and
    without notifying anyone. None on an unknown/author-soft-deleted case."""
    return await _act(session, docente_ctx, report_id, "dismiss", reason)


async def _act(
    session: AsyncSession,
    docente_ctx: UserCtx,
    report_id: int,
    action: str,
    reason: Reason | None,
) -> ActionOutcome | None:
    """Shared resolve-all-open + audit-append. Sole writer of
    `documents.moderation_hidden_at` (arch test); touches no other `documents`
    column."""
    doc_id = (
        await session.execute(
            text(
                "SELECT r.doc_id FROM document_reports r "
                "JOIN documents d ON d.id = r.doc_id "
                "WHERE r.id = :rid AND d.soft_deleted_at IS NULL"
            ),
            {"rid": report_id},
        )
    ).scalar_one_or_none()
    if doc_id is None:
        return None

    if action == "hide":
        await session.execute(
            text("UPDATE documents SET moderation_hidden_at = now() WHERE id = :d"),
            {"d": doc_id},
        )
    elif action == "unhide":
        await session.execute(
            text("UPDATE documents SET moderation_hidden_at = NULL WHERE id = :d"),
            {"d": doc_id},
        )

    action_id = (
        await session.execute(
            text(
                "INSERT INTO moderation_actions "
                "(report_id, docente_user_id, action, reason) "
                "VALUES (:rid, :uid, :action, :reason) RETURNING id"
            ),
            {
                "rid": report_id,
                "uid": docente_ctx.user_id,
                "action": action,
                "reason": reason,
            },
        )
    ).scalar_one()

    await session.execute(
        text(
            "UPDATE document_reports SET status = 'resolved' "
            "WHERE doc_id = :d AND status = 'open'"
        ),
        {"d": doc_id},
    )

    kind = _NOTIFY_KIND.get(action)
    if kind is not None:
        await _notify_authors(
            session, action_id=action_id, doc_id=doc_id, kind=kind, reason=reason
        )

    return ActionOutcome(action_id=action_id, doc_id=doc_id)


async def _notify_authors(
    session: AsyncSession, *, action_id: int, doc_id: int, kind: str, reason: Reason | None
) -> None:
    """Insert one in-app notification per registered author (owner + accepted,
    `user_id NOT NULL`); external authors are skipped. `ON CONFLICT
    (user_id, event_key) DO NOTHING` with `event_key = f"{kind}:{action_id}"`,
    so a retry of the same action never double-notifies any recipient."""
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
