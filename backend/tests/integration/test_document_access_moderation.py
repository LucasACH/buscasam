"""Integration tests for core/document_access.moderation_inspection_where
(issue #77, module map §core/document_access).

The second deliberate reader-policy exception: report-scoped, not
visibility-scoped. The predicate selects the document behind a specific report
regardless of visibility and moderation_hidden_at, for any report status, and
excludes only author-soft-deleted documents. Pinned at the predicate boundary
so the router tests stay focused on transport + role gating.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.core.document_access import moderation_inspection_where
from tests.factories import make_document, make_user


async def _file_report(
    session: AsyncSession, doc_id: int, *, reporter: int, status: str = "open"
) -> int:
    return (
        await session.execute(
            text(
                "INSERT INTO document_reports (doc_id, reporter_user_id, reason, status) "
                "VALUES (:d, :u, 'spam', :st) RETURNING id"
            ),
            {"d": doc_id, "u": reporter, "st": status},
        )
    ).scalar_one()


async def _selects(session: AsyncSession, report_id: int) -> int | None:
    where, params = moderation_inspection_where("d", report_id)
    return (
        await session.execute(
            text(f"SELECT d.id FROM documents d WHERE {where}"), params
        )
    ).scalar_one_or_none()


@pytest.mark.parametrize(
    "factory_kwargs",
    [
        {"visibility": "privado"},
        {"visibility": "interno"},
        {"visibility": "publico", "moderation_hidden": True},
        {"visibility": "privado", "moderation_hidden": True},
    ],
    ids=["privado", "interno", "publico_hidden", "privado_hidden"],
)
async def test_selects_regardless_of_visibility_and_hidden(session, factory_kwargs):
    doc_id = await make_document(session, **factory_kwargs)
    reporter = await make_user(session)
    report_id = await _file_report(session, doc_id, reporter=reporter)

    assert await _selects(session, report_id) == doc_id


@pytest.mark.parametrize("status", ["open", "resolved"])
async def test_selects_for_open_and_resolved_reports(session, status):
    doc_id = await make_document(session, visibility="privado")
    reporter = await make_user(session)
    report_id = await _file_report(session, doc_id, reporter=reporter, status=status)

    assert await _selects(session, report_id) == doc_id


async def test_excludes_author_soft_deleted_doc(session):
    doc_id = await make_document(session, visibility="publico", soft_deleted=True)
    reporter = await make_user(session)
    report_id = await _file_report(session, doc_id, reporter=reporter)

    assert await _selects(session, report_id) is None


async def test_unknown_report_id_selects_nothing(session):
    assert await _selects(session, 999_999) is None
