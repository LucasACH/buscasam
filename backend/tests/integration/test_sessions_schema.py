import secrets

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError


async def _make_user(session, *, google_sub: str = "sub-s1") -> int:
    row = (
        await session.execute(
            text(
                "INSERT INTO users (google_sub, email, hd, role, name) "
                "VALUES (:s, 'u@unsam.edu.ar', 'unsam.edu.ar', 'docente', 'U') "
                "RETURNING id"
            ),
            {"s": google_sub},
        )
    ).scalar_one()
    return row


async def test_sessions_default_expires_at_is_created_at_plus_90_days(session):
    user_id = await _make_user(session)
    sid = secrets.token_bytes(32)

    await session.execute(
        text(
            "INSERT INTO sessions (sid, user_id) VALUES (:sid, :uid)"
        ),
        {"sid": sid, "uid": user_id},
    )
    await session.commit()

    row = (
        await session.execute(
            text(
                "SELECT expires_at = created_at + interval '90 days' AS ok, "
                "last_seen_at IS NOT NULL AS has_last_seen "
                "FROM sessions WHERE sid = :sid"
            ),
            {"sid": sid},
        )
    ).mappings().one()

    assert row["ok"] is True
    assert row["has_last_seen"] is True


async def test_sessions_user_fk_cascades_on_user_delete(session):
    user_id = await _make_user(session, google_sub="sub-cascade")
    sid = secrets.token_bytes(32)
    await session.execute(
        text("INSERT INTO sessions (sid, user_id) VALUES (:sid, :uid)"),
        {"sid": sid, "uid": user_id},
    )
    await session.commit()

    await session.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": user_id})
    await session.commit()

    remaining = (
        await session.execute(
            text("SELECT count(*) FROM sessions WHERE sid = :sid"),
            {"sid": sid},
        )
    ).scalar_one()
    assert remaining == 0


async def test_sessions_expires_at_is_immutable(session):
    user_id = await _make_user(session, google_sub="sub-immut")
    sid = secrets.token_bytes(32)
    await session.execute(
        text("INSERT INTO sessions (sid, user_id) VALUES (:sid, :uid)"),
        {"sid": sid, "uid": user_id},
    )
    await session.commit()

    with pytest.raises(DBAPIError, match="immutable"):
        await session.execute(
            text(
                "UPDATE sessions SET expires_at = expires_at + interval '1 day' "
                "WHERE sid = :sid"
            ),
            {"sid": sid},
        )
        await session.commit()
    await session.rollback()


async def test_sessions_last_seen_at_remains_mutable(session):
    """Sliding-idle refresh must still work — only expires_at is locked."""
    user_id = await _make_user(session, google_sub="sub-slide")
    sid = secrets.token_bytes(32)
    await session.execute(
        text("INSERT INTO sessions (sid, user_id) VALUES (:sid, :uid)"),
        {"sid": sid, "uid": user_id},
    )
    await session.commit()

    await session.execute(
        text(
            "UPDATE sessions SET last_seen_at = now() + interval '1 hour' "
            "WHERE sid = :sid"
        ),
        {"sid": sid},
    )
    await session.commit()


async def test_sessions_user_fk_rejects_unknown_user(session):
    sid = secrets.token_bytes(32)
    with pytest.raises(IntegrityError):
        await session.execute(
            text("INSERT INTO sessions (sid, user_id) VALUES (:sid, 9999999)"),
            {"sid": sid},
        )
        await session.commit()
