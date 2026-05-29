"""Tests for the consolidated notification production surface
(core/notifications). Covers the event-key format every producer/consumer
shares and the (user_id, event_key) idempotency every notify_* helper relies on.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from buscasam.core import notifications
from tests.factories import make_user


def test_coauthor_invite_event_key_format():
    assert notifications.coauthor_invite_event_key(7, 42) == "coauthor_invite:7:42"


async def _payload_rows(session, user_id):
    return (
        await session.execute(
            text(
                "SELECT event_key, kind, payload_json AS payload "
                "FROM notifications WHERE user_id = :uid"
            ),
            {"uid": user_id},
        )
    ).mappings().all()


async def test_notify_coauthor_invite_shape(session):
    uid = await make_user(session)
    await notifications.notify_coauthor_invite(
        session, user_id=uid, doc_id=5, doc_title="Redes", inviter="Ada"
    )
    [row] = await _payload_rows(session, uid)
    assert row["event_key"] == f"coauthor_invite:5:{uid}"
    assert row["kind"] == "coauthor_invite"
    assert row["payload"] == {"doc_title": "Redes", "doc_id": 5, "inviter": "Ada"}


async def test_notify_indexing_failed_shape(session):
    uid = await make_user(session)
    await notifications.notify_indexing_failed(
        session, user_id=uid, doc_id=5, version_id=9, error="corrupted: X"
    )
    [row] = await _payload_rows(session, uid)
    assert row["event_key"] == "processing_failed:9"
    assert row["kind"] == "processing_failed"
    assert row["payload"] == {"doc_id": 5, "version_id": 9, "error": "corrupted: X"}


async def test_notify_headline_refresh_failed_uses_distinct_key_same_kind(session):
    uid = await make_user(session)
    await notifications.notify_headline_refresh_failed(
        session, user_id=uid, doc_id=5, version_id=9, error="exhausted retries: X"
    )
    [row] = await _payload_rows(session, uid)
    # Distinct prefix from indexing failure, so both can coexist on one version…
    assert row["event_key"] == "headline_refresh_failed:9"
    # …but the same kind, so the consumer needs no new branch.
    assert row["kind"] == "processing_failed"


async def test_notify_moderation_action_shape(session):
    uid = await make_user(session)
    await notifications.notify_moderation_action(
        session,
        user_id=uid,
        kind=notifications.DOCUMENT_HIDDEN,
        action_id=3,
        doc_id=5,
        doc_title="Trabajo",
        reason="spam",
    )
    [row] = await _payload_rows(session, uid)
    assert row["event_key"] == "document_hidden:3"
    assert row["kind"] == "document_hidden"
    assert row["payload"] == {"doc_id": 5, "doc_title": "Trabajo", "reason": "spam"}


async def test_moderation_reason_none_serializes_to_json_null(session):
    uid = await make_user(session)
    await notifications.notify_moderation_action(
        session,
        user_id=uid,
        kind=notifications.DOCUMENT_UNHIDDEN,
        action_id=4,
        doc_id=5,
        doc_title="Trabajo",
        reason=None,
    )
    [row] = await _payload_rows(session, uid)
    assert row["payload"]["reason"] is None


@pytest.mark.parametrize(
    "call",
    [
        lambda s, uid: notifications.notify_coauthor_invite(
            s, user_id=uid, doc_id=5, doc_title="T", inviter="A"
        ),
        lambda s, uid: notifications.notify_indexing_failed(
            s, user_id=uid, doc_id=5, version_id=9, error="e"
        ),
        lambda s, uid: notifications.notify_moderation_action(
            s, user_id=uid, kind=notifications.DOCUMENT_HIDDEN, action_id=3,
            doc_id=5, doc_title="T", reason="spam"
        ),
    ],
)
async def test_duplicate_insert_is_idempotent(session, call):
    """Re-emitting the same (user_id, event_key) inserts no second row — the
    single dedup contract every producer leans on (ADR-0010 §9)."""
    uid = await make_user(session)
    await call(session, uid)
    await call(session, uid)
    count = (
        await session.execute(
            text("SELECT count(*) FROM notifications WHERE user_id = :uid"),
            {"uid": uid},
        )
    ).scalar_one()
    assert count == 1
