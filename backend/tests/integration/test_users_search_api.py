"""Integration tests for GET /api/users/search (issue #27)."""
from __future__ import annotations

import base64
import secrets

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from buscasam.api.app import create_app
from buscasam.api.deps import get_session
from buscasam.core import auth
from buscasam.settings import settings
from tests.factories import make_user


@pytest_asyncio.fixture
async def client(session, monkeypatch):
    monkeypatch.setattr(settings, "secret_key", "test-secret")

    async def _session_override():
        yield session

    app = create_app()
    app.dependency_overrides[get_session] = _session_override
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


async def _seed_session(session, user_id: int) -> bytes:
    sid = secrets.token_bytes(32)
    await session.execute(
        text("INSERT INTO sessions (sid, user_id) VALUES (:sid, :uid)"),
        {"sid": sid, "uid": user_id},
    )
    return sid


def _sid_cookie(sid: bytes) -> str:
    return base64.urlsafe_b64encode(sid).rstrip(b"=").decode()


async def test_users_search_returns_matches_excluding_self(client, session):
    searcher_id = await make_user(session, name="Lucas Achaval")
    match_id = await make_user(session, name="Lucas Perez")
    _other_id = await make_user(session, name="Unrelated Person")
    sid = await _seed_session(session, searcher_id)
    await session.commit()

    r = await client.get(
        "/api/users/search",
        params={"q": "Lucas"},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 200
    results = r.json()
    ids = [u["user_id"] for u in results]
    assert match_id in ids
    assert searcher_id not in ids
    for u in results:
        assert set(u.keys()) >= {"user_id", "name", "email_local", "picture_url"}


async def test_users_search_matches_by_email(client, session):
    searcher_id = await make_user(session, name="Lucas Achaval")
    match_id = await make_user(
        session, name="Marcos Achaval", email="machavalrodriguez@unsam-bue.edu.ar"
    )
    sid = await _seed_session(session, searcher_id)
    await session.commit()

    r = await client.get(
        "/api/users/search",
        params={"q": "machavalrodriguez@unsam-bue.edu.ar"},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 200
    assert match_id in [u["user_id"] for u in r.json()]


async def test_users_search_returns_at_most_10(client, session):
    searcher_id = await make_user(session, name="Searcher")
    sid = await _seed_session(session, searcher_id)
    for i in range(15):
        await make_user(session, name=f"Common Name {i}")
    await session.commit()

    r = await client.get(
        "/api/users/search",
        params={"q": "Common"},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 200
    assert len(r.json()) <= 10


async def test_users_search_returns_401_for_invitado(client):
    r = await client.get("/api/users/search", params={"q": "Lucas"})
    assert r.status_code == 401
