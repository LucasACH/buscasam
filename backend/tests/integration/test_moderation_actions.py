"""Integration tests for core/moderation hide/unhide/dismiss (issue #78, module
map §core/moderation). Each action, in one transaction, appends an append-only
moderation_actions row and resolves all open reports on the document; hide
stamps documents.moderation_hidden_at, unhide clears it, dismiss leaves it.
hide/unhide notify every registered author; dismiss notifies no one.
"""
from __future__ import annotations

from sqlalchemy import text

from buscasam.core.auth import UserCtx
from buscasam.core import moderation
from buscasam.core.moderation import dismiss, hide, unhide
from tests.factories import make_document, make_document_author, make_user


def _docente_ctx(user_id: int) -> UserCtx:
    return UserCtx(user_id=user_id, is_unsam=True, role="docente")


async def _file_report(session, doc_id: int, reporter: int, *, status: str = "open") -> int:
    return (
        await session.execute(
            text(
                "INSERT INTO document_reports (doc_id, reporter_user_id, reason, status) "
                "VALUES (:d, :u, 'spam', :st) RETURNING id"
            ),
            {"d": doc_id, "u": reporter, "st": status},
        )
    ).scalar_one()


async def _moderation_hidden_at(session, doc_id: int):
    return (
        await session.execute(
            text("SELECT moderation_hidden_at FROM documents WHERE id = :d"),
            {"d": doc_id},
        )
    ).scalar_one()


async def _report_status(session, report_id: int) -> str:
    return (
        await session.execute(
            text("SELECT status FROM document_reports WHERE id = :r"),
            {"r": report_id},
        )
    ).scalar_one()


async def test_hide_stamps_appends_action_and_resolves_open_reports(session):
    docente = await make_user(session, role="docente")
    doc_id = await make_document(session)
    report_id = await _file_report(session, doc_id, await make_user(session))

    outcome = await hide(session, _docente_ctx(docente), report_id, "spam")

    assert outcome is not None
    assert outcome.doc_id == doc_id
    assert await _moderation_hidden_at(session, doc_id) is not None
    assert await _report_status(session, report_id) == "resolved"
    action = (
        await session.execute(
            text(
                "SELECT report_id, docente_user_id, action, reason "
                "FROM moderation_actions WHERE id = :a"
            ),
            {"a": outcome.action_id},
        )
    ).mappings().one()
    assert dict(action) == {
        "report_id": report_id,
        "docente_user_id": docente,
        "action": "hide",
        "reason": "spam",
    }


async def test_hide_leaves_publication_soft_delete_and_is_current_untouched(session):
    docente = await make_user(session, role="docente")
    doc_id = await make_document(session, publication_status="published")
    await session.execute(
        text(
            "INSERT INTO document_versions "
            "(doc_id, version_no, sha256, original_filename, bytes, mime, "
            " index_status, is_current, first_published_at) "
            "VALUES (:d, 1, decode('aa', 'hex'), 'f.pdf', 1, 'application/pdf', "
            "        'indexed', true, now())"
        ),
        {"d": doc_id},
    )
    report_id = await _file_report(session, doc_id, await make_user(session))

    await hide(session, _docente_ctx(docente), report_id, "spam")

    row = (
        await session.execute(
            text(
                "SELECT publication_status, soft_deleted_at FROM documents WHERE id = :d"
            ),
            {"d": doc_id},
        )
    ).mappings().one()
    assert row["publication_status"] == "published"
    assert row["soft_deleted_at"] is None
    is_current = (
        await session.execute(
            text("SELECT is_current FROM document_versions WHERE doc_id = :d"),
            {"d": doc_id},
        )
    ).scalar_one()
    assert is_current is True


async def test_unhide_clears_column_and_resolves_open_reports(session):
    docente = await make_user(session, role="docente")
    doc_id = await make_document(session, moderation_hidden=True)
    report_id = await _file_report(session, doc_id, await make_user(session))

    outcome = await unhide(session, _docente_ctx(docente), report_id)

    assert outcome is not None
    assert await _moderation_hidden_at(session, doc_id) is None
    assert await _report_status(session, report_id) == "resolved"


async def test_rehide_reunhide_leaves_no_residue_beyond_audit_log(session):
    docente = await make_user(session, role="docente")
    doc_id = await make_document(session)
    ctx = _docente_ctx(docente)

    await hide(session, ctx, await _file_report(session, doc_id, await make_user(session)), "x")
    await unhide(session, ctx, await _file_report(session, doc_id, await make_user(session)))
    await hide(session, ctx, await _file_report(session, doc_id, await make_user(session)), "y")

    assert await _moderation_hidden_at(session, doc_id) is not None
    actions = (
        await session.execute(
            text(
                "SELECT action FROM moderation_actions m "
                "JOIN document_reports r ON r.id = m.report_id "
                "WHERE r.doc_id = :d ORDER BY m.id"
            ),
            {"d": doc_id},
        )
    ).scalars().all()
    assert actions == ["hide", "unhide", "hide"]


async def test_dismiss_resolves_without_changing_column_and_notifies_no_one(session):
    docente = await make_user(session, role="docente")
    doc_id = await make_document(session)
    author = await make_user(session)
    await make_document_author(session, doc_id, user_id=author, status="owner")
    report_id = await _file_report(session, doc_id, await make_user(session))

    await dismiss(session, _docente_ctx(docente), report_id)

    assert await _moderation_hidden_at(session, doc_id) is None
    assert await _report_status(session, report_id) == "resolved"
    count = (
        await session.execute(text("SELECT count(*) FROM notifications"))
    ).scalar_one()
    assert count == 0


async def test_hide_notifies_only_registered_authors(session):
    docente = await make_user(session, role="docente")
    doc_id = await make_document(session, titulo="Trabajo")
    owner = await make_user(session)
    accepted = await make_user(session)
    pending = await make_user(session)
    declined = await make_user(session)
    await make_document_author(session, doc_id, user_id=owner, status="owner")
    await make_document_author(session, doc_id, user_id=accepted, status="accepted")
    await make_document_author(session, doc_id, user_id=pending, status="pending")
    await make_document_author(session, doc_id, user_id=declined, status="declined")
    await make_document_author(session, doc_id, user_id=None, status="external")
    report_id = await _file_report(session, doc_id, await make_user(session))

    outcome = await hide(session, _docente_ctx(docente), report_id, "spam")

    rows = (
        await session.execute(
            text(
                "SELECT user_id, kind, event_key, payload_json AS payload "
                "FROM notifications ORDER BY user_id"
            )
        )
    ).mappings().all()
    assert {r["user_id"] for r in rows} == {owner, accepted}
    for r in rows:
        assert r["kind"] == "document_hidden"
        assert r["event_key"] == f"document_hidden:{outcome.action_id}"
        assert r["payload"] == {
            "doc_title": "Trabajo",
            "doc_id": doc_id,
            "reason": "spam",
        }


async def test_unhide_notifies_with_unhidden_kind(session):
    docente = await make_user(session, role="docente")
    doc_id = await make_document(session, moderation_hidden=True)
    owner = await make_user(session)
    await make_document_author(session, doc_id, user_id=owner, status="owner")
    report_id = await _file_report(session, doc_id, await make_user(session))

    outcome = await unhide(session, _docente_ctx(docente), report_id)

    row = (
        await session.execute(
            text("SELECT kind, event_key FROM notifications WHERE user_id = :u"),
            {"u": owner},
        )
    ).mappings().one()
    assert row["kind"] == "document_unhidden"
    assert row["event_key"] == f"document_unhidden:{outcome.action_id}"


async def test_notify_is_idempotent_on_event_key(session):
    """A retry of the same action's fan-out inserts no duplicate
    (ON CONFLICT (user_id, event_key) DO NOTHING)."""
    docente = await make_user(session, role="docente")
    doc_id = await make_document(session)
    owner = await make_user(session)
    await make_document_author(session, doc_id, user_id=owner, status="owner")
    report_id = await _file_report(session, doc_id, await make_user(session))

    outcome = await hide(session, _docente_ctx(docente), report_id, "spam")
    await moderation._notify_authors(
        session,
        action_id=outcome.action_id,
        doc_id=doc_id,
        kind="document_hidden",
        reason="spam",
    )

    count = (
        await session.execute(
            text("SELECT count(*) FROM notifications WHERE user_id = :u"),
            {"u": owner},
        )
    ).scalar_one()
    assert count == 1


async def test_unknown_report_returns_none(session):
    docente = await make_user(session, role="docente")
    assert await hide(session, _docente_ctx(docente), 999999, "spam") is None


async def test_author_soft_deleted_doc_returns_none(session):
    docente = await make_user(session, role="docente")
    doc_id = await make_document(session, soft_deleted=True)
    report_id = await _file_report(session, doc_id, await make_user(session))

    assert await hide(session, _docente_ctx(docente), report_id, "spam") is None
    # No action row, no column write.
    actions = (
        await session.execute(
            text("SELECT count(*) FROM moderation_actions WHERE report_id = :r"),
            {"r": report_id},
        )
    ).scalar_one()
    assert actions == 0
