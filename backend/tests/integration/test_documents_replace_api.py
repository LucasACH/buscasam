"""Integration tests for POST /api/documents/{id}/replace and the extended
GET /api/documents/{id}/draft candidate field (issue #58)."""
from __future__ import annotations

import base64
import secrets

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from buscasam.api import documents as documents_api
from buscasam.api.app import create_app
from buscasam.api.deps import get_session
from buscasam.core import auth, blob_store
from buscasam.core.extract import PDFEncryptionError
from buscasam.settings import settings
from tests.factories import make_document, make_document_author, make_user

_PLAIN_PDF = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\n"
_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
_ORIGIN = "http://localhost:3000"


@pytest.fixture
def blob_root(tmp_path, monkeypatch):
    root = tmp_path / "blobs"
    root.mkdir()
    monkeypatch.setattr(blob_store, "BLOB_ROOT", root)
    return root


@pytest_asyncio.fixture
async def client(session, monkeypatch, blob_root):
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


async def _seed_published_doc(session, *, owner_id: int) -> int:
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
    return doc_id


async def _version_count(session, doc_id: int) -> int:
    return (
        await session.execute(
            text("SELECT count(*) FROM document_versions WHERE doc_id = :d"),
            {"d": doc_id},
        )
    ).scalar_one()


async def test_replace_valid_pdf_returns_202(client, session, blob_root):
    uid = await make_user(session)
    sid = await _seed_session(session, uid)
    doc_id = await _seed_published_doc(session, owner_id=uid)
    await session.commit()

    r = await client.post(
        f"/api/documents/{doc_id}/replace",
        files={"file": ("nueva.pdf", _PLAIN_PDF, "application/pdf")},
        headers={"origin": _ORIGIN},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 202
    assert await _version_count(session, doc_id) == 2
    candidate = (
        await session.execute(
            text(
                "SELECT index_status, is_current FROM document_versions "
                "WHERE doc_id = :d AND version_no = 2"
            ),
            {"d": doc_id},
        )
    ).mappings().one()
    assert candidate["index_status"] == "pending"
    assert candidate["is_current"] is False


async def test_replace_oversized_returns_413(client, session, blob_root):
    uid = await make_user(session)
    sid = await _seed_session(session, uid)
    doc_id = await _seed_published_doc(session, owner_id=uid)
    await session.commit()
    big = b"%PDF-1.4 " + b"x" * (51 * 1024 * 1024)

    r = await client.post(
        f"/api/documents/{doc_id}/replace",
        files={"file": ("big.pdf", big, "application/pdf")},
        headers={"origin": _ORIGIN},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 413
    assert r.json()["detail"] == "Este archivo supera los 50 MB"
    assert await _version_count(session, doc_id) == 1


async def test_replace_wrong_mime_returns_415(client, session, blob_root):
    uid = await make_user(session)
    sid = await _seed_session(session, uid)
    doc_id = await _seed_published_doc(session, owner_id=uid)
    await session.commit()

    r = await client.post(
        f"/api/documents/{doc_id}/replace",
        files={"file": ("image.pdf", _PNG_BYTES, "application/pdf")},
        headers={"origin": _ORIGIN},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 415
    assert await _version_count(session, doc_id) == 1


async def test_replace_encrypted_pdf_returns_415(
    client, session, blob_root, monkeypatch
):
    uid = await make_user(session)
    sid = await _seed_session(session, uid)
    doc_id = await _seed_published_doc(session, owner_id=uid)
    await session.commit()

    def _raise(_data):
        raise PDFEncryptionError("PDF is password-protected")

    monkeypatch.setattr(documents_api, "probe_encrypted", _raise)

    r = await client.post(
        f"/api/documents/{doc_id}/replace",
        files={"file": ("locked.pdf", _PLAIN_PDF, "application/pdf")},
        headers={"origin": _ORIGIN},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 415
    assert "contraseña" in r.json()["detail"]
    assert await _version_count(session, doc_id) == 1


async def test_replace_without_published_version_returns_409(client, session, blob_root):
    uid = await make_user(session)
    sid = await _seed_session(session, uid)
    # Draft doc with a non-current candidate only — never published.
    doc_id = await make_document(session, publication_status="draft")
    await make_document_author(session, doc_id, user_id=uid, status="owner")
    await session.execute(
        text(
            "INSERT INTO document_versions "
            "(doc_id, version_no, sha256, original_filename, bytes, mime, "
            " uploaded_by, index_status, is_current) "
            "VALUES (:d, 1, decode('aa', 'hex'), 'd.pdf', 1, 'application/pdf', "
            " :u, 'indexed', false)"
        ),
        {"d": doc_id, "u": uid},
    )
    await session.commit()

    r = await client.post(
        f"/api/documents/{doc_id}/replace",
        files={"file": ("nueva.pdf", _PLAIN_PDF, "application/pdf")},
        headers={"origin": _ORIGIN},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 409


async def test_replace_cross_user_returns_404(client, session, blob_root):
    owner = await make_user(session)
    other = await make_user(session)
    other_sid = await _seed_session(session, other)
    doc_id = await _seed_published_doc(session, owner_id=owner)
    await session.commit()

    r = await client.post(
        f"/api/documents/{doc_id}/replace",
        files={"file": ("nueva.pdf", _PLAIN_PDF, "application/pdf")},
        headers={"origin": _ORIGIN},
        cookies={auth.SID_COOKIE: _sid_cookie(other_sid)},
    )

    assert r.status_code == 404


async def test_get_draft_candidate_null_without_candidate(client, session, blob_root):
    uid = await make_user(session)
    sid = await _seed_session(session, uid)
    doc_id = await _seed_published_doc(session, owner_id=uid)
    await session.commit()

    r = await client.get(
        f"/api/documents/{doc_id}/draft",
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 200
    assert r.json()["candidate"] is None


async def test_get_draft_candidate_present_after_replace(client, session, blob_root):
    uid = await make_user(session)
    sid = await _seed_session(session, uid)
    doc_id = await _seed_published_doc(session, owner_id=uid)
    await session.commit()

    await client.post(
        f"/api/documents/{doc_id}/replace",
        files={"file": ("nueva.pdf", _PLAIN_PDF, "application/pdf")},
        headers={"origin": _ORIGIN},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    r = await client.get(
        f"/api/documents/{doc_id}/draft",
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 200
    candidate = r.json()["candidate"]
    assert candidate is not None
    assert candidate["status"] == "processing"
    assert candidate["can_discard"] is True
    assert candidate["can_publish"] is False
