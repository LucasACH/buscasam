"""Integration tests for DELETE /api/documents/{id} (issue #65). Mirrors the
POST /publish edge: 204 for the owner, 404 (no existence leak) for a non-owner,
an accepted coautor, or an unknown id."""
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


async def test_delete_by_owner_returns_204_and_stamps(client, session):
    owner = await make_user(session)
    sid = await _seed_session(session, owner)
    doc_id = await make_document(session, publication_status="published")
    await make_document_author(session, doc_id, user_id=owner, status="owner")
    await session.commit()

    r = await client.delete(
        f"/api/documents/{doc_id}",
        headers={"origin": ORIGIN},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 204
    assert await _soft_deleted_at(session, doc_id) is not None


async def test_delete_by_non_owner_returns_404(client, session):
    owner = await make_user(session)
    other = await make_user(session)
    other_sid = await _seed_session(session, other)
    doc_id = await make_document(session, publication_status="published")
    await make_document_author(session, doc_id, user_id=owner, status="owner")
    await session.commit()

    r = await client.delete(
        f"/api/documents/{doc_id}",
        headers={"origin": ORIGIN},
        cookies={auth.SID_COOKIE: _sid_cookie(other_sid)},
    )

    assert r.status_code == 404
    assert await _soft_deleted_at(session, doc_id) is None


async def test_delete_by_accepted_coautor_returns_404(client, session):
    owner = await make_user(session)
    coautor = await make_user(session)
    coautor_sid = await _seed_session(session, coautor)
    doc_id = await make_document(session, publication_status="published")
    await make_document_author(session, doc_id, user_id=owner, status="owner")
    await make_document_author(session, doc_id, user_id=coautor, status="accepted")
    await session.commit()

    r = await client.delete(
        f"/api/documents/{doc_id}",
        headers={"origin": ORIGIN},
        cookies={auth.SID_COOKIE: _sid_cookie(coautor_sid)},
    )

    assert r.status_code == 404
    assert await _soft_deleted_at(session, doc_id) is None


async def test_delete_unknown_doc_returns_404(client, session):
    owner = await make_user(session)
    sid = await _seed_session(session, owner)
    await session.commit()

    r = await client.delete(
        "/api/documents/999999",
        headers={"origin": ORIGIN},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 404
