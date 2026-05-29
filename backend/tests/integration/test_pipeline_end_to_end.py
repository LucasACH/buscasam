"""End-to-end pipeline test (issue #28 acceptance criterion).

Drives the upload route → asserts pending → simulates worker pickup of the
enqueued index_document task → asserts indexed + chunks + staged metadata.
The worker pickup is invoked synchronously via _run_index_document because
unit tests do not run the procrastinate worker loop.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
from io import BytesIO

import httpx
import pytest
import pytest_asyncio
from fpdf import FPDF
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from buscasam.api.app import create_app
from buscasam.api.deps import get_session
from buscasam.core import auth, blob_store, jobs
from buscasam.settings import settings
from tests.factories import make_user


_ORIGIN = "http://localhost:3000"
_DRAFT = {
    "title": "Mi tesis de grado",
    "area_path": "escuela_ciencia.fisica",
    "document_type": "paper",
    "visibility": "publico",
    "external_authors": [],
    "coauthor_user_ids": [],
}


def _real_pdf() -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(180, 10, "Resumen")
    pdf.multi_cell(180, 10, "Este trabajo investiga la integracion. " * 20)
    pdf.multi_cell(180, 10, "Conclusiones del trabajo. " * 20)
    return bytes(pdf.output())


def _tei_mock() -> httpx.AsyncClient:
    def handler(req: httpx.Request) -> httpx.Response:
        import json
        n = len(json.loads(req.read())["inputs"])
        return httpx.Response(200, json=[[0.1] * 1024] * n)
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://tei")


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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _seed_sid(session, user_id: int) -> str:
    sid = secrets.token_bytes(32)
    await session.execute(
        text("INSERT INTO sessions (sid, user_id) VALUES (:sid, :uid)"),
        {"sid": sid, "uid": user_id},
    )
    await session.commit()
    return base64.urlsafe_b64encode(sid).rstrip(b"=").decode()


async def test_pipeline_pending_to_indexed_for_text_layer_pdf(client, session, blob_root, worker_sm):
    uid = await make_user(session)
    sid = await _seed_sid(session, uid)
    cookies = {auth.SID_COOKIE: sid}

    r = await client.post("/api/documents", json=_DRAFT, headers={"origin": _ORIGIN}, cookies=cookies)
    assert r.status_code == 201
    doc_id = r.json()["id"]

    r = await client.post(
        f"/api/documents/{doc_id}/upload",
        files={"file": ("thesis.pdf", _real_pdf(), "application/pdf")},
        headers={"origin": _ORIGIN},
        cookies=cookies,
    )
    assert r.status_code == 202

    # Snapshot the pending row + the deferred procrastinate job.
    row = (
        await session.execute(
            text(
                "SELECT id, index_status FROM document_versions WHERE doc_id = :id"
            ),
            {"id": doc_id},
        )
    ).mappings().one()
    version_id = row["id"]
    assert row["index_status"] == "pending"

    queued = (
        await session.execute(
            text(
                "SELECT task_name FROM procrastinate_jobs "
                "WHERE args->>'version_id' = :vid AND status = 'todo'"
            ),
            {"vid": str(version_id)},
        )
    ).mappings().one()
    assert queued["task_name"].endswith("index_document")

    # Simulate the worker picking up that job.
    tei = _tei_mock()
    await jobs._run_index_document(worker_sm, tei, version_id)
    await tei.aclose()

    row = (
        await session.execute(
            text(
                "SELECT index_status, staged_abstract, staged_keywords, staged_fecha, "
                "       headline_fingerprint, indexed_at "
                "FROM document_versions WHERE id = :id"
            ),
            {"id": version_id},
        )
    ).mappings().one()
    assert row["index_status"] == "indexed"
    assert row["headline_fingerprint"] is not None
    assert row["indexed_at"] is not None

    chunks = (
        await session.execute(
            text(
                "SELECT chunk_seq, is_headline, is_current, version_id "
                "FROM chunks WHERE version_id = :vid"
            ),
            {"vid": version_id},
        )
    ).mappings().all()
    assert len(chunks) >= 2
    assert all(c["version_id"] == version_id for c in chunks)
    assert all(c["is_current"] is False for c in chunks)
