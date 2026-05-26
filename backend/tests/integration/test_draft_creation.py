"""Integration tests for draft creation and file upload (issue #27)."""
from __future__ import annotations

import base64
import secrets

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from buscasam.api.app import create_app
from buscasam.api.deps import get_session
from buscasam.core import auth, blob_store
from buscasam.settings import settings
from tests.factories import make_user

_PLAIN_PDF = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\n"
_ENCRYPTED_PDF = b"%PDF-1.4\n1 0 obj\n<<\n/Encrypt 2 0 R\n>>\nendobj\n"
_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


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


_VALID_DRAFT = {
    "title": "Mi tesis de grado",
    "area_path": "escuela_ciencia.fisica",
    "document_type": "paper",
    "visibility": "publico",
    "external_authors": [],
    "coauthor_user_ids": [],
}

_ORIGIN = "http://localhost:3000"


async def test_create_draft_returns_201_with_doc_id(client, session):
    uid = await make_user(session)
    sid = await _seed_session(session, uid)
    await session.commit()

    r = await client.post(
        "/api/documents",
        json=_VALID_DRAFT,
        headers={"origin": _ORIGIN},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 201
    doc_id = r.json()["id"]
    assert isinstance(doc_id, int)

    row = (
        await session.execute(
            text("SELECT publication_status FROM documents WHERE id = :id"),
            {"id": doc_id},
        )
    ).mappings().first()
    assert row["publication_status"] == "draft"

    author = (
        await session.execute(
            text("SELECT status, user_id FROM document_authors WHERE doc_id = :id"),
            {"id": doc_id},
        )
    ).mappings().first()
    assert author["status"] == "owner"
    assert author["user_id"] == uid


async def test_create_draft_inserts_pending_coauthor_rows(client, session):
    owner_id = await make_user(session, name="Owner")
    coauthor_id = await make_user(session, name="Coauthor")
    sid = await _seed_session(session, owner_id)
    await session.commit()

    r = await client.post(
        "/api/documents",
        json={**_VALID_DRAFT, "coauthor_user_ids": [coauthor_id]},
        headers={"origin": _ORIGIN},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 201
    doc_id = r.json()["id"]

    rows = (
        await session.execute(
            text(
                "SELECT user_id, status FROM document_authors "
                "WHERE doc_id = :id ORDER BY status"
            ),
            {"id": doc_id},
        )
    ).mappings().all()

    statuses = {r["status"]: r["user_id"] for r in rows}
    assert statuses["owner"] == owner_id
    assert statuses["pending"] == coauthor_id


async def _create_draft(client, session) -> tuple[int, int, bytes]:
    uid = await make_user(session)
    sid = await _seed_session(session, uid)
    await session.commit()
    r = await client.post(
        "/api/documents",
        json=_VALID_DRAFT,
        headers={"origin": _ORIGIN},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )
    assert r.status_code == 201
    return uid, r.json()["id"], sid


async def test_upload_valid_pdf_returns_202_and_creates_pending_version(
    client, session, blob_root
):
    uid, doc_id, sid = await _create_draft(client, session)

    r = await client.post(
        f"/api/documents/{doc_id}/upload",
        files={"file": ("thesis.pdf", _PLAIN_PDF, "application/pdf")},
        headers={"origin": _ORIGIN},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 202

    row = (
        await session.execute(
            text("SELECT index_status, mime FROM document_versions WHERE doc_id = :id"),
            {"id": doc_id},
        )
    ).mappings().first()
    assert row is not None
    assert row["index_status"] == "pending"
    assert row["mime"] == "application/pdf"


async def test_upload_encrypted_pdf_returns_415_no_blob_no_version(
    client, session, blob_root
):
    uid, doc_id, sid = await _create_draft(client, session)

    r = await client.post(
        f"/api/documents/{doc_id}/upload",
        files={"file": ("thesis.pdf", _ENCRYPTED_PDF, "application/pdf")},
        headers={"origin": _ORIGIN},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 415
    assert "contraseña" in r.json()["detail"]

    count = (
        await session.execute(
            text("SELECT COUNT(*) FROM document_versions WHERE doc_id = :id"),
            {"id": doc_id},
        )
    ).scalar_one()
    assert count == 0
    assert not any(blob_root.rglob("*") if blob_root.exists() else [])


async def test_upload_wrong_mime_returns_415_no_version(client, session, blob_root):
    uid, doc_id, sid = await _create_draft(client, session)

    r = await client.post(
        f"/api/documents/{doc_id}/upload",
        files={"file": ("image.pdf", _PNG_BYTES, "application/pdf")},
        headers={"origin": _ORIGIN},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 415

    count = (
        await session.execute(
            text("SELECT COUNT(*) FROM document_versions WHERE doc_id = :id"),
            {"id": doc_id},
        )
    ).scalar_one()
    assert count == 0


async def test_upload_oversized_file_returns_413(client, session, blob_root):
    uid, doc_id, sid = await _create_draft(client, session)
    big = b"%PDF-1.4 " + b"x" * (51 * 1024 * 1024)

    r = await client.post(
        f"/api/documents/{doc_id}/upload",
        files={"file": ("big.pdf", big, "application/pdf")},
        headers={"origin": _ORIGIN},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 413


async def test_upload_to_other_users_doc_returns_404(client, session, blob_root):
    _, doc_id, _ = await _create_draft(client, session)

    other_uid = await make_user(session)
    other_sid = await _seed_session(session, other_uid)
    await session.commit()

    r = await client.post(
        f"/api/documents/{doc_id}/upload",
        files={"file": ("thesis.pdf", _PLAIN_PDF, "application/pdf")},
        headers={"origin": _ORIGIN},
        cookies={auth.SID_COOKIE: _sid_cookie(other_sid)},
    )

    assert r.status_code == 404
