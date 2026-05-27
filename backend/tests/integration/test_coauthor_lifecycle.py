"""Integration tests for core/documents.accept_invitation / decline_invitation
(issue #50, module map §core/documents). Each does an atomic status flip plus a
matching notifications.read_at mark; a non-pending miss raises
InvitationNotPending. The readable-lifecycle guard collapses transitions on
hidden/soft-deleted docs.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from buscasam.core import documents
from buscasam.core.auth import UserCtx
from buscasam.core.jobs import coauthor_invite_event_key
from tests.factories import (
    make_document,
    make_document_author,
    make_notification,
    make_user,
)


def _ctx(user_id: int) -> UserCtx:
    return UserCtx(user_id=user_id, is_unsam=True, role="estudiante")


async def _seed(session, *, status="pending", with_notification=True, **doc_kwargs):
    """Published doc + owner + one coautor (default pending) + its invite
    notification. Returns (doc_id, invitee_user_id, notification_id|None)."""
    owner = await make_user(session, name="Ada")
    invitee = await make_user(session, name="Bob")
    doc_id = await make_document(session, publication_status="published", **doc_kwargs)
    await make_document_author(session, doc_id, user_id=owner, status="owner")
    await make_document_author(session, doc_id, user_id=invitee, status=status)
    nid = None
    if with_notification:
        nid = await make_notification(
            session,
            user_id=invitee,
            kind="coauthor_invite",
            event_key=coauthor_invite_event_key(doc_id, invitee),
        )
    return doc_id, invitee, nid


async def _status(session, doc_id, user_id) -> str:
    return (
        await session.execute(
            text(
                "SELECT status FROM document_authors "
                "WHERE doc_id = :d AND user_id = :u"
            ),
            {"d": doc_id, "u": user_id},
        )
    ).scalar_one()


async def _read_at(session, nid):
    return (
        await session.execute(
            text("SELECT read_at FROM notifications WHERE id = :id"), {"id": nid}
        )
    ).scalar_one()


async def test_accept_flips_status_and_marks_notification_read(session):
    doc_id, invitee, nid = await _seed(session)

    await documents.accept_invitation(session, _ctx(invitee), doc_id)

    assert await _status(session, doc_id, invitee) == "accepted"
    assert await _read_at(session, nid) is not None


async def test_decline_flips_status_and_marks_notification_read(session):
    doc_id, invitee, nid = await _seed(session)

    await documents.decline_invitation(session, _ctx(invitee), doc_id)

    assert await _status(session, doc_id, invitee) == "declined"
    assert await _read_at(session, nid) is not None


async def test_resubmit_on_already_transitioned_raises_not_pending(session):
    """A second accept (or decline) no longer matches status='pending'."""
    doc_id, invitee, _ = await _seed(session)
    await documents.accept_invitation(session, _ctx(invitee), doc_id)

    with pytest.raises(documents.InvitationNotPending):
        await documents.accept_invitation(session, _ctx(invitee), doc_id)
    with pytest.raises(documents.InvitationNotPending):
        await documents.decline_invitation(session, _ctx(invitee), doc_id)
    # the first transition stands, untouched
    assert await _status(session, doc_id, invitee) == "accepted"


async def test_accept_on_deleted_row_raises_not_pending(session):
    """Revoke-while-deciding: the row is gone, so the transition is a 0-row miss."""
    doc_id, invitee, _ = await _seed(session)
    await session.execute(
        text("DELETE FROM document_authors WHERE doc_id = :d AND user_id = :u"),
        {"d": doc_id, "u": invitee},
    )

    with pytest.raises(documents.InvitationNotPending):
        await documents.accept_invitation(session, _ctx(invitee), doc_id)


async def test_accept_on_moderation_hidden_doc_raises_not_pending(session):
    """Readable-lifecycle guard: a hidden doc cannot have an acceptance ratified."""
    doc_id, invitee, _ = await _seed(session, moderation_hidden=True)

    with pytest.raises(documents.InvitationNotPending):
        await documents.accept_invitation(session, _ctx(invitee), doc_id)
    assert await _status(session, doc_id, invitee) == "pending"


async def test_accept_on_soft_deleted_doc_raises_not_pending(session):
    doc_id, invitee, _ = await _seed(session, soft_deleted=True)

    with pytest.raises(documents.InvitationNotPending):
        await documents.accept_invitation(session, _ctx(invitee), doc_id)
    assert await _status(session, doc_id, invitee) == "pending"
