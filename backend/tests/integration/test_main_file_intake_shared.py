"""Integration tests proving /upload and /replace share one main-file intake
path: identical size (413), encrypted-PDF (415), and unsupported-MIME (415)
validation, regardless of the endpoint's domain action."""
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


async def _setup_upload(session) -> tuple[int, bytes]:
    """A draft document the owner can /upload to (no published version yet)."""
    uid = await make_user(session)
    sid = await _seed_session(session, uid)
    doc_id = await make_document(session, publication_status="draft")
    await make_document_author(session, doc_id, user_id=uid, status="owner")
    await session.commit()
    return doc_id, sid


async def _setup_replace(session) -> tuple[int, bytes]:
    """A published document the owner can /replace (one indexed current version)."""
    uid = await make_user(session)
    sid = await _seed_session(session, uid)
    doc_id = await make_document(
        session, publication_status="published", titulo="Trabajo", abstract="Resumen"
    )
    await make_document_author(session, doc_id, user_id=uid, status="owner")
    await session.execute(
        text(
            "INSERT INTO document_versions "
            "(doc_id, version_no, sha256, original_filename, bytes, mime, "
            " uploaded_by, index_status, is_current, first_published_at, indexed_at) "
            "VALUES (:d, 1, decode('aa', 'hex'), 'original.pdf', 2048, "
            " 'application/pdf', :u, 'indexed', true, now(), now())"
        ),
        {"d": doc_id, "u": uid},
    )
    await session.commit()
    return doc_id, sid


# Each endpoint with the setup that puts its document in the state where intake
# runs: upload on a fresh draft, replace on a published document.
_ENDPOINTS = [
    ("/upload", _setup_upload, 0),  # base version count after setup
    ("/replace", _setup_replace, 1),
]


async def _version_count(session, doc_id: int) -> int:
    return (
        await session.execute(
            text("SELECT count(*) FROM document_versions WHERE doc_id = :d"),
            {"d": doc_id},
        )
    ).scalar_one()


@pytest.mark.parametrize("action, setup, base_count", _ENDPOINTS)
async def test_intake_oversized_returns_413(
    client, session, blob_root, action, setup, base_count
):
    doc_id, sid = await setup(session)
    big = b"%PDF-1.4 " + b"x" * (51 * 1024 * 1024)

    r = await client.post(
        f"/api/documents/{doc_id}{action}",
        files={"file": ("big.pdf", big, "application/pdf")},
        headers={"origin": _ORIGIN},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 413
    assert r.json()["detail"] == "Este archivo supera los 50 MB"
    assert await _version_count(session, doc_id) == base_count
    assert not [p for p in blob_root.rglob("*") if p.is_file()]


@pytest.mark.parametrize("action, setup, base_count", _ENDPOINTS)
async def test_intake_encrypted_pdf_returns_415(
    client, session, blob_root, monkeypatch, action, setup, base_count
):
    doc_id, sid = await setup(session)

    def _raise(_data):
        raise PDFEncryptionError("PDF is password-protected")

    monkeypatch.setattr(documents_api, "probe_encrypted", _raise)

    r = await client.post(
        f"/api/documents/{doc_id}{action}",
        files={"file": ("locked.pdf", _PLAIN_PDF, "application/pdf")},
        headers={"origin": _ORIGIN},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 415
    assert "contraseña" in r.json()["detail"]
    assert await _version_count(session, doc_id) == base_count
    assert not [p for p in blob_root.rglob("*") if p.is_file()]


@pytest.mark.parametrize("action, setup, base_count", _ENDPOINTS)
async def test_intake_unsupported_mime_returns_415(
    client, session, blob_root, action, setup, base_count
):
    doc_id, sid = await setup(session)

    r = await client.post(
        f"/api/documents/{doc_id}{action}",
        files={"file": ("image.pdf", _PNG_BYTES, "application/pdf")},
        headers={"origin": _ORIGIN},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 415
    assert r.json()["detail"] == "Formato no permitido"
    assert await _version_count(session, doc_id) == base_count
    # The rejected blob was discarded (unreferenced) by the shared intake path.
    assert not [p for p in blob_root.rglob("*") if p.is_file()]
