"""Integration tests for DELETE /api/documents/{id}/candidate and the
post-discard GET /draft / version-download surfaces (issue #59)."""
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


async def _seed_published_with_candidate(session, *, owner_id: int) -> int:
    doc_id = await make_document(
        session, publication_status="published", titulo="Trabajo", abstract="Resumen"
    )
    await make_document_author(session, doc_id, user_id=owner_id, status="owner")
    await session.execute(
        text(
            "INSERT INTO document_versions "
            "(doc_id, version_no, sha256, original_filename, bytes, mime, "
            " uploaded_by, index_status, is_current, first_published_at, indexed_at) "
            "VALUES (:d, 1, decode('aa', 'hex'), 'original.pdf', 2048, "
            " 'application/pdf', :u, 'indexed', true, now(), now())"
        ),
        {"d": doc_id, "u": owner_id},
    )
    await session.execute(
        text(
            "INSERT INTO document_versions "
            "(doc_id, version_no, sha256, original_filename, bytes, mime, "
            " uploaded_by, index_status, is_current) "
            "VALUES (:d, 2, decode('bb', 'hex'), 'nueva.pdf', 4096, "
            " 'application/pdf', :u, 'processing', false)"
        ),
        {"d": doc_id, "u": owner_id},
    )
    return doc_id


async def test_discard_candidate_returns_204(client, session):
    uid = await make_user(session)
    sid = await _seed_session(session, uid)
    doc_id = await _seed_published_with_candidate(session, owner_id=uid)
    await session.commit()

    r = await client.delete(
        f"/api/documents/{doc_id}/candidate",
        headers={"origin": ORIGIN},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 204
    status = (
        await session.execute(
            text(
                "SELECT index_status FROM document_versions "
                "WHERE doc_id = :d AND version_no = 2"
            ),
            {"d": doc_id},
        )
    ).scalar_one()
    assert status == "discarded"


async def test_discard_no_candidate_returns_404(client, session):
    uid = await make_user(session)
    sid = await _seed_session(session, uid)
    doc_id = await make_document(session, publication_status="published")
    await make_document_author(session, doc_id, user_id=uid, status="owner")
    await session.execute(
        text(
            "INSERT INTO document_versions "
            "(doc_id, version_no, sha256, original_filename, bytes, mime, "
            " uploaded_by, index_status, is_current, first_published_at) "
            "VALUES (:d, 1, decode('aa', 'hex'), 'original.pdf', 2048, "
            " 'application/pdf', :u, 'indexed', true, now())"
        ),
        {"d": doc_id, "u": uid},
    )
    await session.commit()

    r = await client.delete(
        f"/api/documents/{doc_id}/candidate",
        headers={"origin": ORIGIN},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 404


async def test_discard_cross_user_returns_404(client, session):
    owner = await make_user(session)
    other = await make_user(session)
    other_sid = await _seed_session(session, other)
    doc_id = await _seed_published_with_candidate(session, owner_id=owner)
    await session.commit()

    r = await client.delete(
        f"/api/documents/{doc_id}/candidate",
        headers={"origin": ORIGIN},
        cookies={auth.SID_COOKIE: _sid_cookie(other_sid)},
    )

    assert r.status_code == 404
    # The candidate is untouched by the cross-user attempt.
    status = (
        await session.execute(
            text(
                "SELECT index_status FROM document_versions "
                "WHERE doc_id = :d AND version_no = 2"
            ),
            {"d": doc_id},
        )
    ).scalar_one()
    assert status == "processing"


async def test_draft_candidate_null_after_discard(client, session):
    uid = await make_user(session)
    sid = await _seed_session(session, uid)
    doc_id = await _seed_published_with_candidate(session, owner_id=uid)
    await session.commit()

    await client.delete(
        f"/api/documents/{doc_id}/candidate",
        headers={"origin": ORIGIN},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )
    r = await client.get(
        f"/api/documents/{doc_id}/draft",
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 200
    body = r.json()
    assert body["candidate"] is None
    # The discarded version never had first_published_at, so it is absent from
    # the Versiones list — only the published current version remains.
    assert [v["n"] for v in body["versions"]] == [1]


async def test_discarded_version_not_downloadable(client, session):
    uid = await make_user(session)
    sid = await _seed_session(session, uid)
    doc_id = await _seed_published_with_candidate(session, owner_id=uid)
    await session.commit()

    await client.delete(
        f"/api/documents/{doc_id}/candidate",
        headers={"origin": ORIGIN},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    # The discarded candidate is not exposed at any historic-version index.
    r = await client.get(
        f"/api/docs/{doc_id}/versions/2/download",
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )
    assert r.status_code == 404
