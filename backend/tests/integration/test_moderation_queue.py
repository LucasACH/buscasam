"""Integration tests for core/moderation.list_open_reports (issue #76, module
map §core/moderation). The Docente triage queue read: one entry per reported
document with title, reason(s), first/last reported_at, and reporter count,
ordered for triage. Resolved-only documents do not appear.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text

from buscasam.core.moderation import list_open_reports
from tests.factories import make_document, make_user


async def _file_report(
    session,
    doc_id: int,
    reporter_user_id: int,
    reason: str,
    *,
    status: str = "open",
    created_at: datetime | None = None,
) -> int:
    return (
        await session.execute(
            text(
                "INSERT INTO document_reports "
                "(doc_id, reporter_user_id, reason, status, created_at) "
                "VALUES (:d, :u, :r, :s, COALESCE(:c, now())) RETURNING id"
            ),
            {"d": doc_id, "u": reporter_user_id, "r": reason, "s": status, "c": created_at},
        )
    ).scalar_one()


async def test_one_entry_per_doc_with_multi_reporter_count_and_fields(session):
    doc = await make_document(session, titulo="Doc A")
    r1 = await make_user(session)
    r2 = await make_user(session)
    t1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t2 = datetime(2026, 1, 5, tzinfo=timezone.utc)
    await _file_report(session, doc, r1, "spam", created_at=t1)
    await _file_report(session, doc, r2, "plagio", created_at=t2)

    entries = await list_open_reports(session)

    assert len(entries) == 1
    e = entries[0]
    assert e.doc_id == doc
    assert e.title == "Doc A"
    assert e.report_count == 2
    assert e.reasons == ["plagio", "spam"]
    assert e.first_reported_at == t1
    assert e.last_reported_at == t2


async def test_entry_carries_a_representative_open_report_id(session):
    doc = await make_document(session, titulo="Doc A")
    id1 = await _file_report(session, doc, await make_user(session), "spam")
    id2 = await _file_report(session, doc, await make_user(session), "plagio")

    [entry] = await list_open_reports(session)

    assert entry.report_id == max(id1, id2)


async def test_mixed_open_and_resolved_reports_aggregate_only_open(session):
    doc = await make_document(session, titulo="Mixed doc")
    t1 = datetime(2026, 1, 3, tzinfo=timezone.utc)
    t2 = datetime(2026, 1, 7, tzinfo=timezone.utc)
    await _file_report(session, doc, await make_user(session), "spam", created_at=t1)
    await _file_report(session, doc, await make_user(session), "plagio", created_at=t2)
    await _file_report(
        session, doc, await make_user(session), "error",
        status="resolved", created_at=datetime(2026, 1, 20, tzinfo=timezone.utc),
    )

    entries = await list_open_reports(session)

    assert len(entries) == 1
    e = entries[0]
    assert e.report_count == 2
    assert e.reasons == ["plagio", "spam"]
    assert e.first_reported_at == t1
    assert e.last_reported_at == t2


async def test_resolved_only_document_does_not_appear(session):
    resolved = await make_document(session, titulo="Resolved doc")
    rr = await make_user(session)
    await _file_report(session, resolved, rr, "spam", status="resolved")

    open_doc = await make_document(session, titulo="Open doc")
    ro = await make_user(session)
    await _file_report(session, open_doc, ro, "plagio")

    entries = await list_open_reports(session)

    assert [e.doc_id for e in entries] == [open_doc]


async def test_ordered_for_triage_count_then_recency(session):
    most_reported = await make_document(session, titulo="Most reported")
    await _file_report(session, most_reported, await make_user(session), "spam")
    await _file_report(session, most_reported, await make_user(session), "plagio")

    recent = await make_document(session, titulo="Recent")
    await _file_report(
        session, recent, await make_user(session), "spam",
        created_at=datetime(2026, 1, 10, tzinfo=timezone.utc),
    )

    old = await make_document(session, titulo="Old")
    await _file_report(
        session, old, await make_user(session), "spam",
        created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )

    entries = await list_open_reports(session)

    assert [e.doc_id for e in entries] == [most_reported, recent, old]
