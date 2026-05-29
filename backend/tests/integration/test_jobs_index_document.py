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


async def test_index_document_happy_path_indexes_pdf(session, blob_root, worker_sm):
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

    await jobs._run_index_document(worker_sm, tei, version_id)
    await tei.aclose()

    status = (
        await session.execute(
            text("SELECT index_status FROM document_versions WHERE id = :id"),
            {"id": version_id},
        )
    ).scalar_one()
    assert status == "indexed"


async def test_index_document_corrupted_pdf_marks_failed_and_notifies(session, blob_root, worker_sm):
    payload = b"%PDF-1.4 totally not a real pdf body"
    sha_hex, sha_bytes = _persist_blob(blob_root, payload)
    uid, doc_id, version_id = await _seed_version(
        session, sha_bytes=sha_bytes, mime="application/pdf"
    )
    tei = _tei_mock()

    await jobs._run_index_document(worker_sm, tei, version_id)
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
    session, blob_root, worker_sm
):
    payload = b"%PDF-1.4 garbage"
    sha_hex, sha_bytes = _persist_blob(blob_root, payload)
    uid, doc_id, version_id = await _seed_version(
        session, sha_bytes=sha_bytes, mime="application/pdf"
    )
    tei = _tei_mock()

    await jobs._run_index_document(worker_sm, tei, version_id)
    await jobs._run_index_document(worker_sm, tei, version_id)
    await tei.aclose()

    count = (
        await session.execute(
            text("SELECT COUNT(*) FROM notifications WHERE event_key = :ek"),
            {"ek": f"processing_failed:{version_id}"},
        )
    ).scalar_one()
    assert count == 1


async def test_index_document_ocr_required_reenqueues_on_ocr_queue(
    session, blob_root, worker_sm, monkeypatch
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

    await jobs._run_index_document(worker_sm, tei, version_id)
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
    session, blob_root, worker_sm
):
    """ADR-0007 §9 / PRD story 34: empty body extraction is not a failure."""
    payload = _docx_bytes([""])  # truly empty document
    sha_hex, sha_bytes = _persist_blob(blob_root, payload)
    uid, doc_id, version_id = await _seed_version(
        session, sha_bytes=sha_bytes, mime=_DOCX_MIME
    )
    tei = _tei_mock()

    await jobs._run_index_document(worker_sm, tei, version_id)
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


async def test_index_document_happy_path_indexes_docx(session, blob_root, worker_sm):
    payload = _docx_bytes([
        "Resumen",
        "Este trabajo investiga la integración de Postgres y procrastinate.",
        "Conclusiones",
        "El sistema funciona como se esperaba.",
    ])
    sha_hex, sha_bytes = _persist_blob(blob_root, payload)
    uid, doc_id, version_id = await _seed_version(session, sha_bytes=sha_bytes, mime=_DOCX_MIME)
    tei = _tei_mock()

    await jobs._run_index_document(worker_sm, tei, version_id)
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


async def test_index_document_persists_local_metadata_llm_output(
    session, blob_root, worker_sm, monkeypatch
):
    payload = _docx_bytes([
        "Este documento analiza grafos de coautoría académica.",
        "El método compara redes, componentes y centralidad.",
    ])
    sha_hex, sha_bytes = _persist_blob(blob_root, payload)
    uid, doc_id, version_id = await _seed_version(
        session, sha_bytes=sha_bytes, mime=_DOCX_MIME
    )
    tei = _tei_mock()
    monkeypatch.setattr(jobs.extractmod.settings, "metadata_llm_enabled", True)

    async def _llm(client, doc, fallback):
        return jobs.extractmod._LlmMetadata(
            abstract="Resumen limpio del modelo local.",
            keywords=["grafos", "Este trabajo", "centralidad"],
        )

    monkeypatch.setattr(jobs.extractmod, "_call_metadata_llm", _llm)

    await jobs._run_index_document(worker_sm, tei, version_id)
    await tei.aclose()

    row = (
        await session.execute(
            text(
                "SELECT index_status, staged_abstract, staged_keywords "
                "FROM document_versions WHERE id = :id"
            ),
            {"id": version_id},
        )
    ).mappings().one()
    assert row["index_status"] == "indexed"
    assert row["staged_abstract"] == "Resumen limpio del modelo local."
    assert row["staged_keywords"] == ["grafos", "centralidad"]


async def test_index_document_metadata_llm_timeout_still_indexes(
    session, blob_root, worker_sm, monkeypatch
):
    payload = _docx_bytes([
        "Primer párrafo usado como resumen heurístico.",
        "Texto sobre indexación y búsqueda académica.",
    ])
    sha_hex, sha_bytes = _persist_blob(blob_root, payload)
    uid, doc_id, version_id = await _seed_version(
        session, sha_bytes=sha_bytes, mime=_DOCX_MIME
    )
    tei = _tei_mock()
    monkeypatch.setattr(jobs.extractmod.settings, "metadata_llm_enabled", True)

    async def _timeout(client, doc, fallback):
        raise httpx.TimeoutException("slow local model")

    monkeypatch.setattr(jobs.extractmod, "_call_metadata_llm", _timeout)

    await jobs._run_index_document(worker_sm, tei, version_id)
    await tei.aclose()

    row = (
        await session.execute(
            text(
                "SELECT index_status, staged_abstract, headline_fingerprint "
                "FROM document_versions WHERE id = :id"
            ),
            {"id": version_id},
        )
    ).mappings().one()
    assert row["index_status"] == "indexed"
    assert row["staged_abstract"].startswith("Primer párrafo")
    assert row["headline_fingerprint"] is not None


async def test_index_document_duplicate_success_is_no_op(session, blob_root, worker_sm):
    payload = _docx_bytes([
        "Resumen",
        "Este trabajo debe indexarse una sola vez aunque el job se repita.",
    ])
    sha_hex, sha_bytes = _persist_blob(blob_root, payload)
    uid, doc_id, version_id = await _seed_version(
        session, sha_bytes=sha_bytes, mime=_DOCX_MIME
    )
    tei = _tei_mock()

    await jobs._run_index_document(worker_sm, tei, version_id)
    first_chunks = (
        await session.execute(
            text(
                "SELECT chunk_seq, body_text FROM chunks "
                "WHERE version_id = :vid ORDER BY chunk_seq"
            ),
            {"vid": version_id},
        )
    ).all()

    await jobs._run_index_document(worker_sm, tei, version_id)
    await tei.aclose()

    second_chunks = (
        await session.execute(
            text(
                "SELECT chunk_seq, body_text FROM chunks "
                "WHERE version_id = :vid ORDER BY chunk_seq"
            ),
            {"vid": version_id},
        )
    ).all()
    assert second_chunks == first_chunks


async def test_default_and_ocr_completion_share_retry_safe_indexed_result(
    session, blob_root, worker_sm, monkeypatch
):
    import sys
    from types import ModuleType, SimpleNamespace

    from buscasam.core.extract import ExtractedDoc

    payload = b"source"
    sha_hex, sha_bytes = _persist_blob(blob_root, payload)
    uid, doc_id, default_id = await _seed_version(
        session, sha_bytes=sha_bytes, mime=_DOCX_MIME
    )
    uid, doc_id, ocr_id = await _seed_version(
        session, sha_bytes=sha_bytes, mime="application/pdf"
    )
    await session.execute(
        text("UPDATE document_versions SET index_status = 'processing' WHERE id = :id"),
        {"id": ocr_id},
    )

    async def _extract(sha, mime):
        return ExtractedDoc(
            text="Resumen\nTexto equivalente para ambas rutas.",
            paragraph_breaks=[],
            page_breaks=[],
            raw_metadata={},
        )

    monkeypatch.setattr(jobs.extractmod, "extract", _extract)

    async def _open_for_send(sha):
        yield b"%PDF-1.4 source"

    async def _put_stream(stream, *, max_bytes):
        async for _ in stream:
            pass
        return SimpleNamespace(sha256="ocr-output")

    deleted: list[str] = []

    async def _discard(session, sha):
        deleted.append(sha)

    monkeypatch.setattr(jobs.blob_store, "open_for_send", _open_for_send)
    monkeypatch.setattr(jobs.blob_store, "put_stream", _put_stream)
    monkeypatch.setattr(jobs.blob_store, "discard_if_unreferenced", _discard)

    ocr_runs: list[bool] = []

    def _ocr(source, output, **kwargs):
        ocr_runs.append(True)
        output.write(b"%PDF-1.4 ocr")

    class _ExitCodeException(Exception):
        pass

    ocr_module = ModuleType("ocrmypdf")
    ocr_module.ocr = _ocr
    exceptions_module = ModuleType("ocrmypdf.exceptions")
    exceptions_module.ExitCodeException = _ExitCodeException
    monkeypatch.setitem(sys.modules, "ocrmypdf", ocr_module)
    monkeypatch.setitem(sys.modules, "ocrmypdf.exceptions", exceptions_module)

    tei = _tei_mock()
    await jobs._run_index_document(worker_sm, tei, default_id)
    await jobs._run_ocr_index_document(worker_sm, tei, ocr_id)
    await jobs._run_index_document(worker_sm, tei, default_id)
    await jobs._run_ocr_index_document(worker_sm, tei, ocr_id)
    await tei.aclose()

    async def _result(version_id):
        row = (
            await session.execute(
                text(
                    "SELECT index_status, staged_abstract, staged_keywords, "
                    "headline_fingerprint FROM document_versions WHERE id = :id"
                ),
                {"id": version_id},
            )
        ).one()
        chunks = (
            await session.execute(
                text(
                    "SELECT chunk_seq, is_headline, body_text FROM chunks "
                    "WHERE version_id = :id ORDER BY chunk_seq"
                ),
                {"id": version_id},
            )
        ).all()
        return row, chunks

    assert await _result(ocr_id) == await _result(default_id)
    assert len(ocr_runs) == 1
    assert deleted == ["ocr-output"]
