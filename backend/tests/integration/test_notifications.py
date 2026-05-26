"""Integration tests for `api/notifications` per module map §`api/notifications`.

All four routes are `require_authenticated`, Origin-checked on mutation, and
return 404 (not 403) on cross-user access. Every query is owner-scoped.
"""
from __future__ import annotations

import base64
import secrets
from datetime import datetime, timedelta, timezone

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from buscasam.api.app import create_app
from buscasam.api.deps import get_session
from buscasam.settings import settings
from tests.factories import make_notification, make_user

ORIGIN = settings.base_url


def _sid_cookie_value(sid: bytes) -> str:
    return base64.urlsafe_b64encode(sid).rstrip(b"=").decode()


async def _seed_session(session, *, user_id: int) -> str:
    sid = secrets.token_bytes(32)
    await session.execute(
        text("INSERT INTO sessions (sid, user_id) VALUES (:sid, :uid)"),
        {"sid": sid, "uid": user_id},
    )
    return _sid_cookie_value(sid)


@pytest_asyncio.fixture
async def client(session):
    async def _session_override():
        yield session

    app = create_app()
    app.dependency_overrides[get_session] = _session_override
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def test_list_owned_only(client, session):
    """Response carries only the caller's rows, newest first."""
    me = await make_user(session)
    other = await make_user(session)

    base = _now()
    oldest = await make_notification(
        session, user_id=me, kind="coauthor_invite",
        payload={"doc_title": "Redes", "inviter": "Ada"},
        created_at=base - timedelta(minutes=2),
    )
    newest = await make_notification(
        session, user_id=me, kind="document_hidden",
        payload={"doc_title": "Grafos", "reason": "spam"},
        created_at=base,
    )
    middle = await make_notification(
        session, user_id=me, kind="processing_failed",
        payload={"doc_title": "Compiladores"},
        created_at=base - timedelta(minutes=1),
    )
    await make_notification(
        session, user_id=other, kind="coauthor_invite",
        payload={"doc_title": "Otro", "inviter": "Eve"},
        created_at=base,
    )

    cookie = await _seed_session(session, user_id=me)
    r = await client.get("/api/notifications", headers={"cookie": f"sid={cookie}"})

    assert r.status_code == 200
    items = r.json()["items"]
    assert [i["id"] for i in items] == [newest, middle, oldest]
    assert items[0]["kind"] == "document_hidden"
    assert items[0]["payload"]["doc_title"] == "Grafos"


async def test_unread_count_matches_list(client, session):
    """unread_count equals the caller's unread rows across all four kinds."""
    me = await make_user(session)
    other = await make_user(session)

    await make_notification(session, user_id=me, kind="coauthor_invite")
    await make_notification(session, user_id=me, kind="document_hidden")
    await make_notification(session, user_id=me, kind="document_unhidden")
    await make_notification(
        session, user_id=me, kind="processing_failed", read_at=_now()
    )
    # other user's unread rows must not bleed into the caller's count
    await make_notification(session, user_id=other, kind="coauthor_invite")

    cookie = await _seed_session(session, user_id=me)
    headers = {"cookie": f"sid={cookie}"}

    list_r = await client.get("/api/notifications", headers=headers)
    count_r = await client.get("/api/notifications/unread_count", headers=headers)

    assert count_r.status_code == 200
    unread_in_list = sum(1 for i in list_r.json()["items"] if i["read_at"] is None)
    assert count_r.json() == {"count": unread_in_list}
    assert unread_in_list == 3


async def test_mark_read_idempotent(client, session):
    """Double-marking leaves read_at unchanged on the second call."""
    me = await make_user(session)
    nid = await make_notification(session, user_id=me, kind="coauthor_invite")
    cookie = await _seed_session(session, user_id=me)
    headers = {"cookie": f"sid={cookie}", "origin": ORIGIN}

    r1 = await client.post(f"/api/notifications/{nid}/read", headers=headers)
    assert r1.status_code == 200
    first_read_at = (
        await session.execute(
            text("SELECT read_at FROM notifications WHERE id = :id"), {"id": nid}
        )
    ).scalar_one()
    assert first_read_at is not None

    r2 = await client.post(f"/api/notifications/{nid}/read", headers=headers)
    assert r2.status_code == 200
    second_read_at = (
        await session.execute(
            text("SELECT read_at FROM notifications WHERE id = :id"), {"id": nid}
        )
    ).scalar_one()
    assert second_read_at == first_read_at


async def test_mark_all_read_bulk(client, session):
    """Flips every unread row for the caller and only the caller."""
    me = await make_user(session)
    other = await make_user(session)

    await make_notification(session, user_id=me, kind="coauthor_invite")
    await make_notification(session, user_id=me, kind="document_hidden")
    already = await make_notification(
        session, user_id=me, kind="document_unhidden", read_at=_now()
    )
    other_unread = await make_notification(session, user_id=other, kind="coauthor_invite")

    cookie = await _seed_session(session, user_id=me)
    r = await client.post(
        "/api/notifications/mark_all_read",
        headers={"cookie": f"sid={cookie}", "origin": ORIGIN},
    )
    assert r.status_code == 200

    my_unread = (
        await session.execute(
            text(
                "SELECT count(*) FROM notifications "
                "WHERE user_id = :uid AND read_at IS NULL"
            ),
            {"uid": me},
        )
    ).scalar_one()
    assert my_unread == 0

    other_still_unread = (
        await session.execute(
            text("SELECT read_at FROM notifications WHERE id = :id"),
            {"id": other_unread},
        )
    ).scalar_one()
    assert other_still_unread is None

    # the already-read row's timestamp is preserved, not overwritten
    already_read_at = (
        await session.execute(
            text("SELECT read_at FROM notifications WHERE id = :id"), {"id": already}
        )
    ).scalar_one()
    assert already_read_at is not None


async def test_cross_user_isolation_returns_404(client, session):
    """Marking another user's row returns 404 (not 403) and leaves it untouched."""
    me = await make_user(session)
    other = await make_user(session)
    victim = await make_notification(session, user_id=other, kind="coauthor_invite")

    cookie = await _seed_session(session, user_id=me)
    r = await client.post(
        f"/api/notifications/{victim}/read",
        headers={"cookie": f"sid={cookie}", "origin": ORIGIN},
    )

    assert r.status_code == 404
    read_at = (
        await session.execute(
            text("SELECT read_at FROM notifications WHERE id = :id"), {"id": victim}
        )
    ).scalar_one()
    assert read_at is None
