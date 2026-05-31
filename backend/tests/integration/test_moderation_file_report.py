"""Integration tests for core/moderation.file_report (issue #75, module map
§core/moderation). A reporter files an `open` report gated by `readable_where`
(ADR-0010 §7); a second open report by the same reporter on the same doc is a
harmless no-op (unique partial index); a non-readable doc raises
DocumentNotReadable (router → 404)."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from buscasam.core import moderation
from buscasam.core.auth import UserCtx
from tests.factories import make_document, make_document_author, make_user


def _ctx(user_id: int, *, role: str = "estudiante") -> UserCtx:
    return UserCtx(user_id=user_id, is_unsam=True, role=role)


async def _reports(session, doc_id: int) -> list:
    return (
        await session.execute(
            text(
                "SELECT reporter_user_id, reason, status FROM document_reports "
                "WHERE doc_id = :d ORDER BY id"
            ),
            {"d": doc_id},
        )
    ).all()


async def test_file_report_on_readable_published_doc_creates_one_open_row(session):
    doc_id = await make_document(session, visibility="publico")
    reporter = await make_user(session)

    await moderation.file_report(session, _ctx(reporter), doc_id, "spam")

    rows = await _reports(session, doc_id)
    assert rows == [(reporter, "spam", "open")]


async def test_second_open_report_by_same_reporter_is_a_no_op(session):
    doc_id = await make_document(session, visibility="publico")
    reporter = await make_user(session)
    await moderation.file_report(session, _ctx(reporter), doc_id, "spam")

    await moderation.file_report(session, _ctx(reporter), doc_id, "plagio")

    # The unique partial index swallows the second open report; the first stands.
    rows = await _reports(session, doc_id)
    assert rows == [(reporter, "spam", "open")]


async def test_file_report_on_non_readable_doc_raises(session):
    doc_id = await make_document(session, visibility="privado")
    reporter = await make_user(session)

    with pytest.raises(moderation.DocumentNotReadable):
        await moderation.file_report(session, _ctx(reporter), doc_id, "spam")

    assert await _reports(session, doc_id) == []


async def test_owner_may_not_report_own_doc(session):
    doc_id = await make_document(session, visibility="privado")
    owner = await make_user(session)
    await make_document_author(session, doc_id, user_id=owner, status="owner")

    with pytest.raises(moderation.OwnDocumentReport):
        await moderation.file_report(session, _ctx(owner), doc_id, "error")

    assert await _reports(session, doc_id) == []


async def test_new_report_accepted_after_prior_resolved(session):
    doc_id = await make_document(session, visibility="publico")
    reporter = await make_user(session)
    await moderation.file_report(session, _ctx(reporter), doc_id, "spam")
    await session.execute(
        text("UPDATE document_reports SET status = 'resolved' WHERE doc_id = :d"),
        {"d": doc_id},
    )

    await moderation.file_report(session, _ctx(reporter), doc_id, "plagio")

    rows = await _reports(session, doc_id)
    assert rows == [
        (reporter, "spam", "resolved"),
        (reporter, "plagio", "open"),
    ]
