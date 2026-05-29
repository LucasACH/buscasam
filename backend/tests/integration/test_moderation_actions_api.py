"""Integration tests for api/moderation action endpoints (issue #78, module map
§api/moderation). POST …/{report_id}/{hide,unhide,dismiss} → 204 | 404 | 403.
Reason is required on hide, optional on unhide/dismiss; every domain miss is a
uniform 404, role failure a 403.
"""
from __future__ import annotations

import base64
import secrets

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from buscasam.api.app import create_app
from buscasam.api.deps import get_session
from buscasam.settings import settings
from tests.factories import make_document, make_user

ORIGIN = settings.base_url


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


def _headers(cookie: str) -> dict:
    return {"cookie": f"sid={cookie}", "origin": ORIGIN}


async def _docente_cookie(session) -> str:
    return await _sid_cookie(session, await make_user(session, role="docente"))


async def _file_report(session, doc_id: int) -> int:
    reporter = await make_user(session)
    return (
        await session.execute(
            text(
                "INSERT INTO document_reports (doc_id, reporter_user_id, reason) "
                "VALUES (:d, :u, 'spam') RETURNING id"
            ),
            {"d": doc_id, "u": reporter},
        )
    ).scalar_one()


async def test_hide_returns_204_and_stamps(client, session):
    doc_id = await make_document(session)
    report_id = await _file_report(session, doc_id)
    cookie = await _docente_cookie(session)

    r = await client.post(
        f"/api/moderation/reports/{report_id}/hide",
        json={"reason": "spam"},
        headers=_headers(cookie),
    )

    assert r.status_code == 204
    hidden = (
        await session.execute(
            text("SELECT moderation_hidden_at FROM documents WHERE id = :d"),
            {"d": doc_id},
        )
    ).scalar_one()
    assert hidden is not None


@pytest.mark.parametrize("action", ["unhide", "dismiss"])
async def test_unhide_and_dismiss_accept_null_reason(client, session, action):
    doc_id = await make_document(session, moderation_hidden=True)
    report_id = await _file_report(session, doc_id)
    cookie = await _docente_cookie(session)

    r = await client.post(
        f"/api/moderation/reports/{report_id}/{action}",
        json={},
        headers=_headers(cookie),
    )

    assert r.status_code == 204


@pytest.mark.parametrize("body", [{}, {"reason": ""}])
async def test_hide_without_reason_is_rejected(client, session, body):
    doc_id = await make_document(session)
    report_id = await _file_report(session, doc_id)
    cookie = await _docente_cookie(session)

    r = await client.post(
        f"/api/moderation/reports/{report_id}/hide",
        json=body,
        headers=_headers(cookie),
    )

    assert r.status_code == 422


@pytest.mark.parametrize("action", ["hide", "unhide", "dismiss"])
async def test_unknown_report_returns_404(client, session, action):
    cookie = await _docente_cookie(session)

    r = await client.post(
        f"/api/moderation/reports/999999/{action}",
        json={"reason": "spam"},
        headers=_headers(cookie),
    )

    assert r.status_code == 404


@pytest.mark.parametrize("action", ["hide", "unhide", "dismiss"])
async def test_author_soft_deleted_doc_returns_404(client, session, action):
    doc_id = await make_document(session, soft_deleted=True)
    report_id = await _file_report(session, doc_id)
    cookie = await _docente_cookie(session)

    r = await client.post(
        f"/api/moderation/reports/{report_id}/{action}",
        json={"reason": "spam"},
        headers=_headers(cookie),
    )

    assert r.status_code == 404


@pytest.mark.parametrize("action", ["hide", "unhide", "dismiss"])
async def test_non_docente_returns_403(client, session, action):
    doc_id = await make_document(session)
    report_id = await _file_report(session, doc_id)
    cookie = await _sid_cookie(session, await make_user(session, role="estudiante"))

    r = await client.post(
        f"/api/moderation/reports/{report_id}/{action}",
        json={"reason": "spam"},
        headers=_headers(cookie),
    )

    assert r.status_code == 403


@pytest.mark.parametrize("action", ["hide", "unhide", "dismiss"])
async def test_unauthenticated_returns_401(client, session, action):
    doc_id = await make_document(session)
    report_id = await _file_report(session, doc_id)
    await session.commit()

    r = await client.post(
        f"/api/moderation/reports/{report_id}/{action}", json={"reason": "spam"}
    )

    assert r.status_code == 401
