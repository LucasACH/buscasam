"""Integration tests for POST /api/documents/{id}/retry-indexing and the
failure-kind / retry_available_at fields on GET /draft."""

from __future__ import annotations

import base64
import secrets
from datetime import timedelta

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from buscasam.api.app import create_app
from buscasam.api.deps import get_session
from buscasam.core import auth
from buscasam.core.documents import MAX_INDEX_RETRIES, RETRY_COOLDOWN
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


async def _seed_failed_draft(
    session,
    *,
    owner_id: int,
    kind: str = "system",
    failed_ago: timedelta = RETRY_COOLDOWN + timedelta(minutes=1),
    retry_count: int = 0,
) -> int:
    doc_id = await make_document(session, publication_status="draft")
    await make_document_author(session, doc_id, user_id=owner_id, status="owner")
    await session.execute(
        text(
            "INSERT INTO document_versions "
            "(doc_id, version_no, sha256, original_filename, bytes, mime, "
            " uploaded_by, index_status, index_error, index_error_kind, "
            " index_failed_at, index_retry_count) "
            "VALUES (:d, 1, :sha, 'f.pdf', 1024, 'application/pdf', :u, "
            " 'failed', 'exhausted retries: ConnectError', :kind, now() - :ago, "
            " :rc)"
        ),
        {
            "d": doc_id,
            "sha": secrets.token_bytes(32),
            "u": owner_id,
            "kind": kind,
            "ago": failed_ago,
            "rc": retry_count,
        },
    )
    return doc_id


async def test_retry_returns_204_and_resets_to_pending(client, session):
    uid = await make_user(session)
    sid = await _seed_session(session, uid)
    doc_id = await _seed_failed_draft(session, owner_id=uid)
    await session.commit()

    r = await client.post(
        f"/api/documents/{doc_id}/retry-indexing",
        headers={"origin": ORIGIN},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 204
    row = (
        (
            await session.execute(
                text(
                    "SELECT index_status, index_error, index_error_kind, "
                    "  index_failed_at "
                    "FROM document_versions WHERE doc_id = :d"
                ),
                {"d": doc_id},
            )
        )
        .mappings()
        .one()
    )
    assert row["index_status"] == "pending"
    assert row["index_error"] is None
    assert row["index_error_kind"] is None
    assert row["index_failed_at"] is None


async def test_retry_file_failure_returns_409_not_retriable(client, session):
    uid = await make_user(session)
    sid = await _seed_session(session, uid)
    doc_id = await _seed_failed_draft(session, owner_id=uid, kind="file")
    await session.commit()

    r = await client.post(
        f"/api/documents/{doc_id}/retry-indexing",
        headers={"origin": ORIGIN},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 409
    assert r.json()["detail"]["reason"] == "not_retriable"


async def test_retry_past_limit_returns_409_retry_limit(client, session):
    uid = await make_user(session)
    sid = await _seed_session(session, uid)
    doc_id = await _seed_failed_draft(
        session, owner_id=uid, retry_count=MAX_INDEX_RETRIES
    )
    await session.commit()

    r = await client.post(
        f"/api/documents/{doc_id}/retry-indexing",
        headers={"origin": ORIGIN},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 409
    assert r.json()["detail"]["reason"] == "retry_limit"


async def test_retry_inside_cooldown_returns_409_retry_cooldown(client, session):
    uid = await make_user(session)
    sid = await _seed_session(session, uid)
    doc_id = await _seed_failed_draft(
        session, owner_id=uid, failed_ago=timedelta(minutes=1)
    )
    await session.commit()

    r = await client.post(
        f"/api/documents/{doc_id}/retry-indexing",
        headers={"origin": ORIGIN},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 409
    assert r.json()["detail"]["reason"] == "retry_cooldown"


async def test_retry_cross_user_returns_404(client, session):
    owner = await make_user(session)
    other = await make_user(session)
    other_sid = await _seed_session(session, other)
    doc_id = await _seed_failed_draft(session, owner_id=owner)
    await session.commit()

    r = await client.post(
        f"/api/documents/{doc_id}/retry-indexing",
        headers={"origin": ORIGIN},
        cookies={auth.SID_COOKIE: _sid_cookie(other_sid)},
    )

    assert r.status_code == 404
    # The failed row is untouched by the cross-user attempt.
    status = (
        await session.execute(
            text("SELECT index_status FROM document_versions WHERE doc_id = :d"),
            {"d": doc_id},
        )
    ).scalar_one()
    assert status == "failed"


async def test_draft_surfaces_failure_kind_and_retry_available_at(client, session):
    uid = await make_user(session)
    sid = await _seed_session(session, uid)
    doc_id = await _seed_failed_draft(session, owner_id=uid)
    await session.commit()

    r = await client.get(
        f"/api/documents/{doc_id}/draft",
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 200
    body = r.json()
    assert body["index_status"] == "failed"
    assert body["index_failure_kind"] == "system"
    assert body["publish_gate_reason"] == "processing_failed"
    assert body["retry_remaining"] == MAX_INDEX_RETRIES
    expected = (
        await session.execute(
            text(
                "SELECT index_failed_at + :cd FROM document_versions "
                "WHERE doc_id = :d"
            ),
            {"cd": RETRY_COOLDOWN, "d": doc_id},
        )
    ).scalar_one()
    assert body["retry_available_at"] == expected.isoformat()
