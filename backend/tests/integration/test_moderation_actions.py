"""Integration tests for core/moderation hide/unhide/dismiss (issue #78, module
map §core/moderation). The Docente acts on a report — the action is auditable
(`moderation_actions`), resolves the document's open reports in one transaction,
and notifies registered authors on hide/unhide. `core/moderation` is the sole
writer of `documents.moderation_hidden_at`."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from buscasam.core import moderation
from buscasam.core.auth import UserCtx
from tests.factories import make_document, make_document_author, make_user


def _docente(user_id: int) -> UserCtx:
    return UserCtx(user_id=user_id, is_unsam=True, role="docente")


async def _open_report(session, doc_id: int, reporter: int, reason: str = "spam") -> int:
    return (
        await session.execute(
            text(
                "INSERT INTO document_reports (doc_id, reporter_user_id, reason) "
                "VALUES (:d, :u, :r) RETURNING id"
            ),
            {"d": doc_id, "u": reporter, "r": reason},
        )
    ).scalar_one()


async def _doc_row(session, doc_id: int):
    return (
        await session.execute(
            text(
                "SELECT moderation_hidden_at, soft_deleted_at, publication_status "
                "FROM documents WHERE id = :d"
            ),
            {"d": doc_id},
        )
    ).mappings().one()


async def _actions(session, report_id: int):
    return (
        await session.execute(
            text(
                "SELECT docente_user_id, action, reason FROM moderation_actions "
                "WHERE report_id = :r ORDER BY id"
            ),
            {"r": report_id},
        )
    ).all()


async def _statuses(session, doc_id: int):
    return (
        await session.execute(
            text(
                "SELECT status FROM document_reports WHERE doc_id = :d ORDER BY id"
            ),
            {"d": doc_id},
        )
    ).scalars().all()


async def test_hide_stamps_column_appends_action_and_resolves_open_reports(session):
    doc_id = await make_document(session, visibility="publico")
    docente = await make_user(session, role="docente")
    r1 = await _open_report(session, doc_id, await make_user(session))
    await _open_report(session, doc_id, await make_user(session), "plagio")

    await moderation.hide(session, _docente(docente), r1, "contenido_inadecuado")

    row = await _doc_row(session, doc_id)
    assert row["moderation_hidden_at"] is not None
    assert await _actions(session, r1) == [
        (docente, "hide", "contenido_inadecuado")
    ]
    # All open reports on the document are resolved, not just the acted one.
    assert await _statuses(session, doc_id) == ["resolved", "resolved"]


async def _notif_count(session) -> int:
    return (
        await session.execute(text("SELECT count(*) FROM notifications"))
    ).scalar_one()


async def test_dismiss_resolves_reports_without_hiding_and_notifies_no_one(session):
    doc_id = await make_document(session, visibility="publico")
    docente = await make_user(session, role="docente")
    owner = await make_user(session)
    await make_document_author(session, doc_id, user_id=owner, status="owner")
    r1 = await _open_report(session, doc_id, await make_user(session))
    await _open_report(session, doc_id, await make_user(session), "plagio")

    await moderation.dismiss(session, _docente(docente), r1)

    row = await _doc_row(session, doc_id)
    assert row["moderation_hidden_at"] is None
    assert await _statuses(session, doc_id) == ["resolved", "resolved"]
    assert await _actions(session, r1) == [(docente, "dismiss", None)]
    assert await _notif_count(session) == 0


async def _notifs(session):
    return (
        await session.execute(
            text(
                "SELECT user_id, event_key, kind, payload_json AS payload "
                "FROM notifications ORDER BY user_id"
            )
        )
    ).mappings().all()


async def test_hide_notifies_each_registered_author_once(session):
    doc_id = await make_document(session, visibility="publico", titulo="Mi paper")
    docente = await make_user(session, role="docente")
    owner = await make_user(session)
    accepted = await make_user(session)
    pending = await make_user(session)
    declined = await make_user(session)
    await make_document_author(session, doc_id, user_id=owner, status="owner")
    await make_document_author(session, doc_id, user_id=accepted, status="accepted")
    await make_document_author(session, doc_id, user_id=pending, status="pending")
    await make_document_author(session, doc_id, user_id=declined, status="declined")
    await make_document_author(session, doc_id, user_id=None, status="external")
    r1 = await _open_report(session, doc_id, await make_user(session))

    outcome = await moderation.hide(session, _docente(docente), r1, "spam")

    rows = await _notifs(session)
    # Only owner + accepted (registered, user_id NOT NULL) are notified.
    assert {r["user_id"] for r in rows} == {owner, accepted}
    for r in rows:
        assert r["kind"] == "document_hidden"
        assert r["event_key"] == f"document_hidden:{outcome.action_id}"
        assert r["payload"] == {"doc_id": doc_id, "doc_title": "Mi paper", "reason": "spam"}


async def test_unhide_notifies_with_unhidden_kind(session):
    doc_id = await make_document(session, visibility="publico")
    docente = await make_user(session, role="docente")
    owner = await make_user(session)
    await make_document_author(session, doc_id, user_id=owner, status="owner")
    r1 = await _open_report(session, doc_id, await make_user(session))
    await moderation.hide(session, _docente(docente), r1, "spam")

    outcome = await moderation.unhide(session, _docente(docente), r1)

    row = (
        await session.execute(
            text(
                "SELECT kind, event_key FROM notifications "
                "WHERE kind = 'document_unhidden' AND user_id = :u"
            ),
            {"u": owner},
        )
    ).mappings().one()
    assert row["event_key"] == f"document_unhidden:{outcome.action_id}"


async def test_notify_idempotent_on_action_id(session):
    doc_id = await make_document(session, visibility="publico")
    docente = await make_user(session, role="docente")
    owner = await make_user(session)
    await make_document_author(session, doc_id, user_id=owner, status="owner")
    r1 = await _open_report(session, doc_id, await make_user(session))
    outcome = await moderation.hide(session, _docente(docente), r1, "spam")

    # A retry of the same action id (transaction replay) inserts no duplicate.
    await moderation._notify_authors(session, doc_id, outcome.action_id, "document_hidden", "spam")

    assert await _notif_count(session) == 1


@pytest.mark.parametrize("action", ["hide", "unhide", "dismiss"])
async def test_action_on_unknown_report_returns_none(session, action):
    docente = await make_user(session, role="docente")

    outcome = await getattr(moderation, action)(session, _docente(docente), 999999, "spam")

    assert outcome is None


@pytest.mark.parametrize("action", ["hide", "unhide", "dismiss"])
async def test_action_on_author_soft_deleted_doc_returns_none(session, action):
    doc_id = await make_document(session, visibility="publico", soft_deleted=True)
    docente = await make_user(session, role="docente")
    r1 = await _open_report(session, doc_id, await make_user(session))

    outcome = await getattr(moderation, action)(session, _docente(docente), r1, "spam")

    assert outcome is None
    # Moderation cannot resurrect or mutate removed content: no action, no change.
    assert await _actions(session, r1) == []
    assert (await _doc_row(session, doc_id))["moderation_hidden_at"] is None


async def _current_version_id(session, doc_id: int):
    return (
        await session.execute(
            text(
                "SELECT id FROM document_versions "
                "WHERE doc_id = :d AND is_current"
            ),
            {"d": doc_id},
        )
    ).scalar_one_or_none()


async def test_hide_leaves_publication_status_soft_delete_and_is_current_unchanged(session):
    doc_id = await make_document(
        session, visibility="publico", publication_status="published"
    )
    before_current = await _current_version_id(session, doc_id)
    r1 = await _open_report(session, doc_id, await make_user(session))

    await moderation.hide(session, _docente(await make_user(session, role="docente")), r1, "spam")

    row = await _doc_row(session, doc_id)
    assert row["publication_status"] == "published"
    assert row["soft_deleted_at"] is None
    assert await _current_version_id(session, doc_id) == before_current


async def test_unhide_clears_column_and_resolves_open_reports(session):
    doc_id = await make_document(session, visibility="publico")
    docente = await make_user(session, role="docente")
    r1 = await _open_report(session, doc_id, await make_user(session))
    await moderation.hide(session, _docente(docente), r1, "spam")
    # A fresh report arrives after the hide; unhide must settle it too.
    await _open_report(session, doc_id, await make_user(session), "error")

    await moderation.unhide(session, _docente(docente), r1)

    assert (await _doc_row(session, doc_id))["moderation_hidden_at"] is None
    assert await _statuses(session, doc_id) == ["resolved", "resolved"]
    assert await _actions(session, r1) == [
        (docente, "hide", "spam"),
        (docente, "unhide", None),
    ]


async def test_rehide_reunhide_leaves_no_residue_beyond_audit_log(session):
    doc_id = await make_document(session, visibility="publico")
    docente = await make_user(session, role="docente")
    r1 = await _open_report(session, doc_id, await make_user(session))

    await moderation.hide(session, _docente(docente), r1, "spam")
    await moderation.unhide(session, _docente(docente), r1)
    await moderation.hide(session, _docente(docente), r1, "plagio")
    await moderation.unhide(session, _docente(docente), r1)

    # The column is back to clean; only the append-only log accumulates.
    assert (await _doc_row(session, doc_id))["moderation_hidden_at"] is None
    assert [a[1] for a in await _actions(session, r1)] == [
        "hide",
        "unhide",
        "hide",
        "unhide",
    ]
