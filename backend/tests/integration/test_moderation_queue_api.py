"""Integration tests for api/moderation GET /queue (issue #76, module map
§api/moderation). Docente-gated triage read: 200 for a Docente, 403 for a
non-Docente authenticated user, 401 for an anonymous caller.
"""
from __future__ import annotations

import base64
import secrets

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from buscasam.api.app import create_app
from buscasam.api.deps import get_session
from tests.factories import make_document, make_user


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


async def _sid_cookie(session, user_id: int) -> str:
    sid = secrets.token_bytes(32)
    await session.execute(
        text("INSERT INTO sessions (sid, user_id) VALUES (:sid, :uid)"),
        {"sid": sid, "uid": user_id},
    )
    return base64.urlsafe_b64encode(sid).rstrip(b"=").decode()


async def _file_report(session, doc_id: int, reporter_user_id: int, reason: str) -> None:
    await session.execute(
        text(
            "INSERT INTO document_reports (doc_id, reporter_user_id, reason) "
            "VALUES (:d, :u, :r)"
        ),
        {"d": doc_id, "u": reporter_user_id, "r": reason},
    )


async def test_queue_as_docente_returns_200_with_entries(client, session):
    doc = await make_document(session, titulo="Doc A")
    await _file_report(session, doc, await make_user(session), "spam")
    docente = await make_user(session, role="docente")
    cookie = await _sid_cookie(session, docente)

    r = await client.get("/api/moderation/queue", cookies={"sid": cookie})

    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["doc_id"] == doc
    assert items[0]["title"] == "Doc A"
    assert items[0]["reasons"] == ["spam"]
    assert items[0]["report_count"] == 1


async def test_queue_as_non_docente_returns_403(client, session):
    estudiante = await make_user(session, role="estudiante")
    cookie = await _sid_cookie(session, estudiante)

    r = await client.get("/api/moderation/queue", cookies={"sid": cookie})

    assert r.status_code == 403


async def test_queue_anonymous_returns_401(client, session):
    r = await client.get("/api/moderation/queue")

    assert r.status_code == 401
