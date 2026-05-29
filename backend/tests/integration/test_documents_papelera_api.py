"""Integration tests for the Papelera HTTP edge (issue #66):
POST /api/documents/{id}/restore (204 owner / 404 otherwise) and
GET /api/me/documents/deleted (200 list[DeletedDocDTO] incl. purge_at)."""
from __future__ import annotations

import base64
import secrets
from datetime import datetime, timedelta

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from buscasam.api.app import create_app
from buscasam.api.deps import get_session
from buscasam.core import auth
from buscasam.settings import settings
from tests.factories import make_document, make_document_author, make_user

ORIGIN = settings.base_url


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


async def _soft_deleted_at(session, doc_id: int):
    return (
        await session.execute(
            text("SELECT soft_deleted_at FROM documents WHERE id = :id"),
            {"id": doc_id},
        )
    ).scalar_one()


async def test_restore_by_owner_returns_204_and_clears(client, session):
    owner = await make_user(session)
    sid = await _seed_session(session, owner)
    doc_id = await make_document(session, soft_deleted=True)
    await make_document_author(session, doc_id, user_id=owner, status="owner")
    await session.commit()

    r = await client.post(
        f"/api/documents/{doc_id}/restore",
        headers={"origin": ORIGIN},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 204
    assert await _soft_deleted_at(session, doc_id) is None


async def test_restore_by_non_owner_returns_404(client, session):
    owner = await make_user(session)
    other = await make_user(session)
    other_sid = await _seed_session(session, other)
    doc_id = await make_document(session, soft_deleted=True)
    await make_document_author(session, doc_id, user_id=owner, status="owner")
    await session.commit()

    r = await client.post(
        f"/api/documents/{doc_id}/restore",
        headers={"origin": ORIGIN},
        cookies={auth.SID_COOKIE: _sid_cookie(other_sid)},
    )

    assert r.status_code == 404
    assert await _soft_deleted_at(session, doc_id) is not None


async def test_restore_of_live_document_returns_404(client, session):
    owner = await make_user(session)
    sid = await _seed_session(session, owner)
    doc_id = await make_document(session, soft_deleted=False)
    await make_document_author(session, doc_id, user_id=owner, status="owner")
    await session.commit()

    r = await client.post(
        f"/api/documents/{doc_id}/restore",
        headers={"origin": ORIGIN},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 404


async def test_deleted_list_returns_own_docs_with_purge_at(client, session):
    owner = await make_user(session)
    other = await make_user(session)
    sid = await _seed_session(session, owner)
    mine = await make_document(session, soft_deleted=True, titulo="Mío eliminado")
    await make_document_author(session, mine, user_id=owner, status="owner")
    theirs = await make_document(session, soft_deleted=True)
    await make_document_author(session, theirs, user_id=other, status="owner")
    await session.commit()

    r = await client.get(
        "/api/me/documents/deleted",
        headers={"origin": ORIGIN},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 200
    body = r.json()
    assert [d["id"] for d in body] == [mine]
    doc = body[0]
    assert doc["title"] == "Mío eliminado"
    # purge_at = soft_deleted_at + 180 días, the server-computed projection. The
    # raw deletion time is read from the DB (the DTO deliberately omits it).
    soft_deleted_at = await _soft_deleted_at(session, mine)
    purge_at = datetime.fromisoformat(doc["purge_at"])
    assert purge_at - soft_deleted_at == timedelta(days=180)


async def test_deleted_list_requires_authentication(client, session):
    r = await client.get("/api/me/documents/deleted", headers={"origin": ORIGIN})
    assert r.status_code == 401
