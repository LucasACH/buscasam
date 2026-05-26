"""Integration tests for the index_document task body (issue #28).

The procrastinate task body is a thin wrapper around _run_index_document so
tests can drive the orchestration directly against the session fixture
without spinning a worker.
"""
from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path

import httpx
import numpy as np
import pytest
from docx import Document as DocxDocument
from sqlalchemy import text

from buscasam.core import blob_store, jobs
from tests.factories import make_document, make_user


_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@pytest.fixture
def blob_root(tmp_path, monkeypatch):
    root = tmp_path / "blobs"
    root.mkdir()
    monkeypatch.setattr(blob_store, "BLOB_ROOT", root)
    return root


def _persist_blob(blob_root: Path, payload: bytes) -> tuple[str, bytes]:
    raw = hashlib.sha256(payload).digest()
    sha_hex = raw.hex()
    final = blob_root / sha_hex[:2] / sha_hex[2:4] / sha_hex
    final.parent.mkdir(parents=True, exist_ok=True)
    final.write_bytes(payload)
    return sha_hex, raw


async def _seed_version(session, *, sha_bytes: bytes, mime: str) -> tuple[int, int, int]:
    """Returns (user_id, doc_id, version_id)."""
    uid = await make_user(session)
    doc_id = await make_document(session, publication_status="draft", titulo="My thesis")
    await session.execute(
        text(
            "INSERT INTO document_authors (doc_id, user_id, display_name, status) "
            "VALUES (:doc_id, :uid, 'Owner', 'owner')"
        ),
        {"doc_id": doc_id, "uid": uid},
    )
    version_id = (
        await session.execute(
            text(
                "INSERT INTO document_versions "
                "(doc_id, version_no, sha256, original_filename, bytes, mime, "
                " uploaded_by, index_status) "
                "VALUES (:doc_id, 1, :sha, 'file', 1024, :mime, :uid, 'pending') "
                "RETURNING id"
            ),
            {"doc_id": doc_id, "sha": sha_bytes, "uid": uid, "mime": mime},
        )
    ).scalar_one()
    return uid, doc_id, version_id


def _docx_bytes(paragraphs: list[str]) -> bytes:
    doc = DocxDocument()
    for p in paragraphs:
        doc.add_paragraph(p)
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _tei_mock() -> httpx.AsyncClient:
    """Returns vectors of zeros — happy-path embedding."""
    def handler(req: httpx.Request) -> httpx.Response:
        body = req.read()
        import json
        payload = json.loads(body)
        n = len(payload["inputs"])
        vec = [0.1] * 1024
        return httpx.Response(200, json=[vec] * n)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://tei")


async def test_index_document_happy_path_indexes_pdf(session, blob_root):
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(180, 10, "Resumen")
    pdf.multi_cell(180, 10, "Este trabajo investiga la integracion. " * 20)
    pdf.multi_cell(180, 10, "Conclusiones del trabajo. " * 20)
    payload = bytes(pdf.output())
    sha_hex, sha_bytes = _persist_blob(blob_root, payload)
    uid, doc_id, version_id = await _seed_version(
        session, sha_bytes=sha_bytes, mime="application/pdf"
    )
    tei = _tei_mock()

    await jobs._run_index_document(session, tei, version_id)
    await tei.aclose()

    status = (
        await session.execute(
            text("SELECT index_status FROM document_versions WHERE id = :id"),
            {"id": version_id},
        )
    ).scalar_one()
    assert status == "indexed"


async def test_index_document_corrupted_pdf_marks_failed_and_notifies(session, blob_root):
    payload = b"%PDF-1.4 totally not a real pdf body"
    sha_hex, sha_bytes = _persist_blob(blob_root, payload)
    uid, doc_id, version_id = await _seed_version(
        session, sha_bytes=sha_bytes, mime="application/pdf"
    )
    tei = _tei_mock()

    await jobs._run_index_document(session, tei, version_id)
    await tei.aclose()

    row = (
        await session.execute(
            text(
                "SELECT index_status, index_error FROM document_versions WHERE id = :id"
            ),
            {"id": version_id},
        )
    ).mappings().one()
    assert row["index_status"] == "failed"
    assert "corrupted" in row["index_error"]

    notif = (
        await session.execute(
            text("SELECT user_id, kind FROM notifications WHERE event_key = :ek"),
            {"ek": f"processing_failed:{version_id}"},
        )
    ).mappings().one()
    assert notif["kind"] == "processing_failed"
    assert notif["user_id"] == uid


async def test_index_document_retry_after_failure_does_not_duplicate_notification(
    session, blob_root
):
    payload = b"%PDF-1.4 garbage"
    sha_hex, sha_bytes = _persist_blob(blob_root, payload)
    uid, doc_id, version_id = await _seed_version(
        session, sha_bytes=sha_bytes, mime="application/pdf"
    )
    tei = _tei_mock()

    await jobs._run_index_document(session, tei, version_id)
    await jobs._run_index_document(session, tei, version_id)
    await tei.aclose()

    count = (
        await session.execute(
            text("SELECT COUNT(*) FROM notifications WHERE event_key = :ek"),
            {"ek": f"processing_failed:{version_id}"},
        )
    ).scalar_one()
    assert count == 1


async def test_index_document_ocr_required_reenqueues_on_ocr_queue(
    session, blob_root, monkeypatch
):
    payload = _docx_bytes(["whatever"])
    sha_hex, sha_bytes = _persist_blob(blob_root, payload)
    uid, doc_id, version_id = await _seed_version(
        session, sha_bytes=sha_bytes, mime=_DOCX_MIME
    )
    tei = _tei_mock()

    from buscasam.core import extract as extractmod

    async def _raise_ocr(sha, mime):
        raise extractmod.OCRRequired(sha)

    monkeypatch.setattr(jobs.extractmod, "extract", _raise_ocr)

    called: list[int] = []

    async def _capture_enqueue(sess, vid):
        called.append(vid)

    monkeypatch.setattr(jobs, "enqueue_ocr_index_document", _capture_enqueue)

    await jobs._run_index_document(session, tei, version_id)
    await tei.aclose()

    assert called == [version_id]

    # version stays in 'processing' — the OCR worker will move it on completion.
    status = (
        await session.execute(
            text("SELECT index_status FROM document_versions WHERE id = :id"),
            {"id": version_id},
        )
    ).scalar_one()
    assert status == "processing"


async def test_index_document_empty_extraction_docx_indexes_with_empty_abstract(
    session, blob_root
):
    """ADR-0007 §9 / PRD story 34: empty body extraction is not a failure."""
    payload = _docx_bytes([""])  # truly empty document
    sha_hex, sha_bytes = _persist_blob(blob_root, payload)
    uid, doc_id, version_id = await _seed_version(
        session, sha_bytes=sha_bytes, mime=_DOCX_MIME
    )
    tei = _tei_mock()

    await jobs._run_index_document(session, tei, version_id)
    await tei.aclose()

    row = (
        await session.execute(
            text(
                "SELECT index_status, staged_abstract, staged_keywords, staged_fecha "
                "FROM document_versions WHERE id = :id"
            ),
            {"id": version_id},
        )
    ).mappings().one()
    assert row["index_status"] == "indexed"
    assert row["staged_abstract"] == ""
    assert row["staged_keywords"] == []
    assert row["staged_fecha"] is None


async def test_index_document_happy_path_indexes_docx(session, blob_root):
    payload = _docx_bytes([
        "Resumen",
        "Este trabajo investiga la integración de Postgres y procrastinate.",
        "Conclusiones",
        "El sistema funciona como se esperaba.",
    ])
    sha_hex, sha_bytes = _persist_blob(blob_root, payload)
    uid, doc_id, version_id = await _seed_version(session, sha_bytes=sha_bytes, mime=_DOCX_MIME)
    tei = _tei_mock()

    await jobs._run_index_document(session, tei, version_id)
    await tei.aclose()

    row = (
        await session.execute(
            text(
                "SELECT index_status, staged_abstract, headline_fingerprint, indexed_at "
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
                "FROM chunks WHERE version_id = :vid ORDER BY chunk_seq"
            ),
            {"vid": version_id},
        )
    ).mappings().all()
    assert len(chunks) >= 2  # at least headline + 1 body
    assert chunks[0]["is_headline"] is True
    assert all(c["version_id"] == version_id for c in chunks)
    assert all(c["is_current"] is False for c in chunks)
