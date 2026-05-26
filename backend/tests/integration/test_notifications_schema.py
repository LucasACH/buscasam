import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


async def _make_user(session, *, google_sub: str) -> int:
    return (
        await session.execute(
            text(
                "INSERT INTO users (google_sub, email, hd, role, name) "
                "VALUES (:s, 'u@unsam.edu.ar', 'unsam.edu.ar', 'docente', 'U') "
                "RETURNING id"
            ),
            {"s": google_sub},
        )
    ).scalar_one()


async def test_notification_row_round_trip(session):
    uid = await _make_user(session, google_sub="sub-n1")
    await session.execute(
        text(
            "INSERT INTO notifications (user_id, event_key, kind, payload_json) "
            "VALUES (:uid, 'evt-1', 'coauthor_invite', "
            "'{\"doc_id\": 7, \"inviter\": \"Ada\"}'::jsonb)"
        ),
        {"uid": uid},
    )
    await session.commit()

    row = (
        await session.execute(
            text(
                "SELECT kind, payload_json->>'inviter' AS inviter, "
                "read_at, created_at IS NOT NULL AS has_created "
                "FROM notifications WHERE user_id = :uid"
            ),
            {"uid": uid},
        )
    ).mappings().one()

    assert row["kind"] == "coauthor_invite"
    assert row["inviter"] == "Ada"
    assert row["read_at"] is None
    assert row["has_created"] is True


async def test_notifications_event_key_is_unique_per_user(session):
    """ADR-0010 §9: unique (user_id, event_key) anchors producer idempotency."""
    uid = await _make_user(session, google_sub="sub-n2")
    await session.execute(
        text(
            "INSERT INTO notifications (user_id, event_key, kind, payload_json) "
            "VALUES (:uid, 'evt-dup', 'document_hidden', '{}'::jsonb)"
        ),
        {"uid": uid},
    )
    await session.commit()

    with pytest.raises(IntegrityError):
        await session.execute(
            text(
                "INSERT INTO notifications (user_id, event_key, kind, payload_json) "
                "VALUES (:uid, 'evt-dup', 'document_hidden', '{}'::jsonb)"
            ),
            {"uid": uid},
        )
        await session.commit()


async def test_notifications_same_event_key_allowed_for_different_users(session):
    """The unique index is per-user, not global."""
    a = await _make_user(session, google_sub="sub-n3a")
    b = await _make_user(session, google_sub="sub-n3b")
    await session.execute(
        text(
            "INSERT INTO notifications (user_id, event_key, kind, payload_json) "
            "VALUES (:a, 'shared-evt', 'coauthor_invite', '{}'::jsonb), "
            "(:b, 'shared-evt', 'coauthor_invite', '{}'::jsonb)"
        ),
        {"a": a, "b": b},
    )
    await session.commit()


async def test_notifications_user_fk_cascades(session):
    uid = await _make_user(session, google_sub="sub-n4")
    await session.execute(
        text(
            "INSERT INTO notifications (user_id, event_key, kind, payload_json) "
            "VALUES (:uid, 'evt-cascade', 'processing_failed', '{}'::jsonb)"
        ),
        {"uid": uid},
    )
    await session.commit()

    await session.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": uid})
    await session.commit()

    count = (
        await session.execute(
            text(
                "SELECT count(*) FROM notifications "
                "WHERE event_key = 'evt-cascade'"
            )
        )
    ).scalar_one()
    assert count == 0
