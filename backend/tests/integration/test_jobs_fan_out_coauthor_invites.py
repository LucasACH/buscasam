"""Integration tests for core/jobs.fan_out_coauthor_invites (issue #50,
module map §core/jobs). Drives the plain async core directly, like the other
_run_* job cores. The fan-out inserts one coauthor_invite notification per
pending registered coautor, deduped on the (user_id, event_key) unique index.
"""
from __future__ import annotations

from sqlalchemy import text

from buscasam.core import jobs
from tests.factories import make_document, make_document_author, make_user


async def _seed_pending_invite(session, *, doc_title="Mi trabajo", owner_name="Ada"):
    """Published doc with an owner row and one pending registered coautor.
    Returns (doc_id, owner_user_id, invitee_user_id)."""
    owner = await make_user(session, name=owner_name)
    invitee = await make_user(session, name="Bob")
    doc_id = await make_document(
        session, publication_status="published", titulo=doc_title
    )
    await make_document_author(
        session, doc_id, user_id=owner, status="owner", display_name=owner_name
    )
    await make_document_author(
        session, doc_id, user_id=invitee, status="pending", display_name="Bob"
    )
    return doc_id, owner, invitee


async def test_fan_out_inserts_one_notification_per_pending_invitee(session):
    doc_id, _owner, invitee = await _seed_pending_invite(
        session, doc_title="Redes neuronales", owner_name="Ada Lovelace"
    )

    await jobs._run_fan_out_coauthor_invites(session, doc_id)

    rows = (
        await session.execute(
            text(
                "SELECT user_id, event_key, kind, payload_json AS payload "
                "FROM notifications WHERE user_id = :uid"
            ),
            {"uid": invitee},
        )
    ).mappings().all()
    assert len(rows) == 1
    row = rows[0]
    assert row["kind"] == "coauthor_invite"
    assert row["event_key"] == f"coauthor_invite:{doc_id}:{invitee}"
    assert row["payload"] == {
        "doc_title": "Redes neuronales",
        "doc_id": doc_id,
        "inviter": "Ada Lovelace",
    }


async def test_fan_out_is_idempotent_across_partial_completion(session):
    """Re-running after partial completion inserts zero duplicate rows and zero
    new rows for already-notified invitees (ON CONFLICT DO NOTHING)."""
    owner = await make_user(session, name="Ada")
    a = await make_user(session, name="A")
    b = await make_user(session, name="B")
    doc_id = await make_document(session, publication_status="published")
    await make_document_author(session, doc_id, user_id=owner, status="owner")
    await make_document_author(session, doc_id, user_id=a, status="pending")
    await make_document_author(session, doc_id, user_id=b, status="pending")

    # First run notifies both; simulates the "already sent" state for a re-run.
    await jobs._run_fan_out_coauthor_invites(session, doc_id)
    await jobs._run_fan_out_coauthor_invites(session, doc_id)

    count = (
        await session.execute(
            text(
                "SELECT count(*) FROM notifications "
                "WHERE kind = 'coauthor_invite' AND event_key LIKE :pat"
            ),
            {"pat": f"coauthor_invite:{doc_id}:%"},
        )
    ).scalar_one()
    assert count == 2


async def test_fan_out_skips_external_and_non_pending(session):
    """Only pending rows with a non-null user_id receive a notification."""
    owner = await make_user(session, name="Ada")
    accepted = await make_user(session, name="Acc")
    declined = await make_user(session, name="Dec")
    doc_id = await make_document(session, publication_status="published")
    await make_document_author(session, doc_id, user_id=owner, status="owner")
    await make_document_author(session, doc_id, user_id=accepted, status="accepted")
    await make_document_author(session, doc_id, user_id=declined, status="declined")
    # External attribution: pending-shaped intent is impossible (user_id NULL),
    # but guard the SELECT predicate against a name-only row anyway.
    await make_document_author(
        session, doc_id, user_id=None, status="external", display_name="Ext"
    )

    await jobs._run_fan_out_coauthor_invites(session, doc_id)

    count = (
        await session.execute(
            text("SELECT count(*) FROM notifications WHERE kind = 'coauthor_invite'")
        )
    ).scalar_one()
    assert count == 0
