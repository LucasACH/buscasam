"""Integration tests for api/moderation POST /reports (issue #75, module map
§api/moderation). require_authenticated + Origin-checked; a readable doc files
an open report (204), a duplicate is a silent 204 no-op, and every non-readable
target maps to a uniform 404 so hidden/private/deleted existence never leaks."""
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
from tests.factories import make_document, make_document_author, make_user

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


async def _reports(session, doc_id: int) -> list:
    return (
        await session.execute(
            text(
                "SELECT reporter_user_id, reason, status FROM document_reports "
                "WHERE doc_id = :d ORDER BY id"
            ),
            {"d": doc_id},
        )
    ).all()


def _headers(cookie: str) -> dict:
    return {"cookie": f"sid={cookie}", "origin": ORIGIN}


async def test_post_report_on_readable_doc_returns_204_and_creates_one_row(
    client, session
):
    doc_id = await make_document(session, visibility="publico")
    reporter = await make_user(session)
    cookie = await _sid_cookie(session, reporter)

    r = await client.post(
        "/api/moderation/reports",
        json={"doc_id": doc_id, "reason": "spam"},
        headers=_headers(cookie),
    )

    assert r.status_code == 204
    assert await _reports(session, doc_id) == [(reporter, "spam", "open")]


async def test_second_post_by_same_reporter_returns_204_and_no_second_row(
    client, session
):
    doc_id = await make_document(session, visibility="publico")
    reporter = await make_user(session)
    cookie = await _sid_cookie(session, reporter)
    headers = _headers(cookie)

    first = await client.post(
        "/api/moderation/reports",
        json={"doc_id": doc_id, "reason": "spam"},
        headers=headers,
    )
    second = await client.post(
        "/api/moderation/reports",
        json={"doc_id": doc_id, "reason": "plagio"},
        headers=headers,
    )

    assert first.status_code == 204
    assert second.status_code == 204
    assert await _reports(session, doc_id) == [(reporter, "spam", "open")]


@pytest.mark.parametrize(
    "factory_kwargs",
    [
        {"visibility": "privado"},
        {"publication_status": "draft"},
        {"soft_deleted": True},
        {"moderation_hidden": True},
    ],
    ids=["privado", "draft", "soft_deleted", "moderation_hidden"],
)
async def test_post_report_on_non_readable_doc_returns_404(
    client, session, factory_kwargs
):
    """A non-author estudiante cannot read any of these; the miss is a uniform
    404, indistinguishable across hidden/private/deleted (no body leak)."""
    doc_id = await make_document(session, **factory_kwargs)
    reporter = await make_user(session, role="estudiante")
    cookie = await _sid_cookie(session, reporter)

    r = await client.post(
        "/api/moderation/reports",
        json={"doc_id": doc_id, "reason": "spam"},
        headers=_headers(cookie),
    )

    assert r.status_code == 404
    assert "login" not in r.text.lower()
    assert await _reports(session, doc_id) == []


async def test_unauthenticated_post_is_rejected(client, session):
    doc_id = await make_document(session, visibility="publico")
    await session.commit()

    r = await client.post(
        "/api/moderation/reports", json={"doc_id": doc_id, "reason": "spam"}
    )

    assert r.status_code == 401
    assert await _reports(session, doc_id) == []


async def test_coauthor_reports_own_privado_doc_returns_204(client, session):
    doc_id = await make_document(session, visibility="privado")
    owner = await make_user(session)
    await make_document_author(session, doc_id, user_id=owner, status="owner")
    cookie = await _sid_cookie(session, owner)

    r = await client.post(
        "/api/moderation/reports",
        json={"doc_id": doc_id, "reason": "error"},
        headers=_headers(cookie),
    )

    assert r.status_code == 204
    assert await _reports(session, doc_id) == [(owner, "error", "open")]


async def test_fresh_report_after_resolving_prior_returns_204_and_new_row(
    client, session
):
    doc_id = await make_document(session, visibility="publico")
    reporter = await make_user(session)
    cookie = await _sid_cookie(session, reporter)
    await client.post(
        "/api/moderation/reports",
        json={"doc_id": doc_id, "reason": "spam"},
        headers=_headers(cookie),
    )
    await session.execute(
        text("UPDATE document_reports SET status = 'resolved' WHERE doc_id = :d"),
        {"d": doc_id},
    )

    r = await client.post(
        "/api/moderation/reports",
        json={"doc_id": doc_id, "reason": "plagio"},
        headers=_headers(cookie),
    )

    assert r.status_code == 204
    assert await _reports(session, doc_id) == [
        (reporter, "spam", "resolved"),
        (reporter, "plagio", "open"),
    ]
