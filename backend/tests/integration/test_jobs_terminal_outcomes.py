"""Convergence of every fatal indexing path on the same state transition.

ADR-0008 §5: recognized parse/OCR failures inside `_run_index_document` /
`_run_ocr_index_document` and exhausted transient failures detected by
`_run_attempt` must all land on `documents.mark_failed` for candidates and
`documents.mark_headline_refresh_failed` for refresh_headline.
"""
from __future__ import annotations

import hashlib
import secrets
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.core import blob_store, documents, jobs
from tests.factories import make_document, make_user


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


def _tei_mock() -> httpx.AsyncClient:
    def handler(req):
        import json
        n = len(json.loads(req.read())["inputs"])
        return httpx.Response(200, json=[[0.1] * 1024] * n)
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://tei")


@pytest_asyncio.fixture
async def worker_resources(session, monkeypatch):
    """Wire `_get_worker_resources` so the wrapper's own sessions share the
    test connection — commits inside the worker land as SAVEPOINTs the test
    can observe before the outer transaction rolls back at teardown."""
    conn = await session.connection()
    tei = _tei_mock()

    def factory():
        return AsyncSession(
            bind=conn,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )

    monkeypatch.setattr(jobs, "_get_worker_resources", lambda: (factory, tei))
    yield
    await tei.aclose()


async def _seed_version(
    session: AsyncSession,
    *,
    sha_bytes: bytes,
    mime: str,
    index_status: str = "pending",
    staged_abstract: str | None = None,
) -> tuple[int, int, int]:
    uid = await make_user(session)
    doc_id = await make_document(session, publication_status="draft", titulo="Doc")
    await session.execute(
        text(
            "INSERT INTO document_authors (doc_id, user_id, display_name, status) "
            "VALUES (:doc, :uid, 'Owner', 'owner')"
        ),
        {"doc": doc_id, "uid": uid},
    )
    version_id = (
        await session.execute(
            text(
                "INSERT INTO document_versions "
                "(doc_id, version_no, sha256, original_filename, bytes, mime, "
                " uploaded_by, index_status, staged_abstract) "
                "VALUES (:doc, 1, :sha, 'file', 1024, :mime, :uid, :st, :sa) "
                "RETURNING id"
            ),
            {
                "doc": doc_id,
                "sha": sha_bytes,
                "uid": uid,
                "mime": mime,
                "st": index_status,
                "sa": staged_abstract,
            },
        )
    ).scalar_one()
    return uid, doc_id, version_id


def _ctx(task, *, attempts: int) -> SimpleNamespace:
    """Minimal JobContext stub for `_run_attempt` — reads `context.task` and
    `context.job.attempts` only."""
    return SimpleNamespace(
        task=task,
        job=SimpleNamespace(attempts=attempts, task_name=task.name),
    )


# --- index_document terminal outcomes --------------------------------------


async def test_index_exhausted_marks_failed_and_notifies(
    session, blob_root, worker_resources, monkeypatch
):
    sha_hex, sha_bytes = _persist_blob(blob_root, b"%PDF-1.4 x")
    uid, doc_id, version_id = await _seed_version(
        session, sha_bytes=sha_bytes, mime="application/pdf"
    )

    async def _boom(sha, mime):
        raise RuntimeError("tei-down")
    monkeypatch.setattr(jobs.extractmod, "extract", _boom)

    # attempts == max_attempts (3) → retry strategy returns None → terminal.
    with pytest.raises(RuntimeError):
        await jobs.index_document(_ctx(jobs.index_document, attempts=3), version_id)

    row = (
        await session.execute(
            text(
                "SELECT index_status, index_error FROM document_versions WHERE id = :id"
            ),
            {"id": version_id},
        )
    ).mappings().one()
    assert row["index_status"] == "failed"
    assert row["index_error"] == "exhausted retries: RuntimeError"

    notif_count = (
        await session.execute(
            text("SELECT COUNT(*) FROM notifications WHERE event_key = :ek"),
            {"ek": f"processing_failed:{version_id}"},
        )
    ).scalar_one()
    assert notif_count == 1


async def test_index_retries_remaining_leaves_candidate_untouched(
    session, blob_root, worker_resources, monkeypatch
):
    sha_hex, sha_bytes = _persist_blob(blob_root, b"%PDF-1.4 x")
    uid, doc_id, version_id = await _seed_version(
        session, sha_bytes=sha_bytes, mime="application/pdf"
    )

    async def _boom(sha, mime):
        raise RuntimeError("transient")
    monkeypatch.setattr(jobs.extractmod, "extract", _boom)

    # attempts < max_attempts → retry strategy schedules a retry → no terminal.
    with pytest.raises(RuntimeError):
        await jobs.index_document(_ctx(jobs.index_document, attempts=0), version_id)

    row = (
        await session.execute(
            text(
                "SELECT index_status, index_error FROM document_versions WHERE id = :id"
            ),
            {"id": version_id},
        )
    ).mappings().one()
    # Worker session rolled back: the `processing` flip from _begin_indexing is
    # undone, so the row stays where the test seeded it.
    assert row["index_status"] == "pending"
    assert row["index_error"] is None

    notif_count = (
        await session.execute(
            text("SELECT COUNT(*) FROM notifications WHERE event_key = :ek"),
            {"ek": f"processing_failed:{version_id}"},
        )
    ).scalar_one()
    assert notif_count == 0


async def test_index_exhausted_duplicate_does_not_duplicate_notification(
    session, blob_root, worker_resources, monkeypatch
):
    sha_hex, sha_bytes = _persist_blob(blob_root, b"%PDF-1.4 x")
    uid, doc_id, version_id = await _seed_version(
        session, sha_bytes=sha_bytes, mime="application/pdf"
    )

    async def _boom(sha, mime):
        raise RuntimeError("tei-down")
    monkeypatch.setattr(jobs.extractmod, "extract", _boom)

    ctx = _ctx(jobs.index_document, attempts=3)
    with pytest.raises(RuntimeError):
        await jobs.index_document(ctx, version_id)
    with pytest.raises(RuntimeError):
        await jobs.index_document(ctx, version_id)

    notif_count = (
        await session.execute(
            text("SELECT COUNT(*) FROM notifications WHERE event_key = :ek"),
            {"ek": f"processing_failed:{version_id}"},
        )
    ).scalar_one()
    assert notif_count == 1


# --- ocr_index_document terminal outcomes ----------------------------------


def _install_ocrmypdf(monkeypatch, *, raises: type[BaseException] | None = None,
                     exit_code_exception: type[BaseException] | None = None):
    exc_type = exit_code_exception or type("_ExitCodeException", (Exception,), {})

    def _ocr(source, output, **kwargs):
        if raises is not None:
            raise raises("ocrmypdf-failed")
        output.write(b"%PDF-1.4 ocr")

    ocr_module = ModuleType("ocrmypdf")
    ocr_module.ocr = _ocr
    exceptions_module = ModuleType("ocrmypdf.exceptions")
    exceptions_module.ExitCodeException = exc_type
    monkeypatch.setitem(sys.modules, "ocrmypdf", ocr_module)
    monkeypatch.setitem(sys.modules, "ocrmypdf.exceptions", exceptions_module)


async def test_ocr_exhausted_marks_failed(
    session, blob_root, worker_resources, monkeypatch
):
    sha_hex, sha_bytes = _persist_blob(blob_root, b"%PDF-1.4 src")
    uid, doc_id, version_id = await _seed_version(
        session, sha_bytes=sha_bytes, mime="application/pdf"
    )

    async def _open_for_send(sha):
        yield b"%PDF-1.4 src"
    monkeypatch.setattr(jobs.blob_store, "open_for_send", _open_for_send)

    _install_ocrmypdf(monkeypatch, raises=RuntimeError)

    with pytest.raises(RuntimeError):
        await jobs.ocr_index_document(
            _ctx(jobs.ocr_index_document, attempts=3), version_id
        )

    row = (
        await session.execute(
            text(
                "SELECT index_status, index_error FROM document_versions WHERE id = :id"
            ),
            {"id": version_id},
        )
    ).mappings().one()
    assert row["index_status"] == "failed"
    assert row["index_error"] == "exhausted retries: RuntimeError"


# --- refresh_headline terminal outcomes ------------------------------------


async def test_headline_exhausted_keeps_indexed_and_notifies(
    session, blob_root, worker_resources, monkeypatch
):
    sha_bytes = secrets.token_bytes(32)
    uid, doc_id, version_id = await _seed_version(
        session,
        sha_bytes=sha_bytes,
        mime="application/pdf",
        index_status="indexed",
        staged_abstract="new abstract",
    )

    async def _boom(tei, body_text, *, kind):
        raise RuntimeError("tei-headline-down")
    monkeypatch.setattr(jobs.embedmod, "embed", _boom)

    with pytest.raises(RuntimeError):
        await jobs.refresh_headline(
            _ctx(jobs.refresh_headline, attempts=3), version_id
        )

    row = (
        await session.execute(
            text(
                "SELECT index_status, index_error FROM document_versions WHERE id = :id"
            ),
            {"id": version_id},
        )
    ).mappings().one()
    # Headline failure must not regress the indexing lifecycle.
    assert row["index_status"] == "indexed"
    assert row["index_error"] is None

    notif_count = (
        await session.execute(
            text("SELECT COUNT(*) FROM notifications WHERE event_key = :ek"),
            {"ek": f"headline_refresh_failed:{version_id}"},
        )
    ).scalar_one()
    assert notif_count == 1


async def test_headline_retries_remaining_does_not_notify(
    session, blob_root, worker_resources, monkeypatch
):
    sha_bytes = secrets.token_bytes(32)
    uid, doc_id, version_id = await _seed_version(
        session,
        sha_bytes=sha_bytes,
        mime="application/pdf",
        index_status="indexed",
        staged_abstract="new abstract",
    )

    async def _boom(tei, body_text, *, kind):
        raise RuntimeError("transient")
    monkeypatch.setattr(jobs.embedmod, "embed", _boom)

    with pytest.raises(RuntimeError):
        await jobs.refresh_headline(
            _ctx(jobs.refresh_headline, attempts=0), version_id
        )

    notif_count = (
        await session.execute(
            text("SELECT COUNT(*) FROM notifications WHERE event_key = :ek"),
            {"ek": f"headline_refresh_failed:{version_id}"},
        )
    ).scalar_one()
    assert notif_count == 0


# --- first-write-wins on mark_failed ----------------------------------------


async def test_mark_failed_first_write_wins(session):
    """A later `exhausted retries:` write must not clobber a prior, more
    specific `corrupted:` cause for the same row."""
    uid = await make_user(session)
    doc_id = await make_document(session, publication_status="draft")
    await session.execute(
        text(
            "INSERT INTO document_authors (doc_id, user_id, display_name, status) "
            "VALUES (:doc, :uid, 'Owner', 'owner')"
        ),
        {"doc": doc_id, "uid": uid},
    )
    sha = secrets.token_bytes(32)
    version_id = (
        await session.execute(
            text(
                "INSERT INTO document_versions "
                "(doc_id, version_no, sha256, original_filename, bytes, mime, "
                " uploaded_by, index_status) "
                "VALUES (:doc, 1, :sha, 'f', 1, 'application/pdf', :uid, 'pending') "
                "RETURNING id"
            ),
            {"doc": doc_id, "sha": sha, "uid": uid},
        )
    ).scalar_one()

    await documents.mark_failed(session, version_id, error="corrupted: PDFSyntaxError")
    await documents.mark_failed(
        session, version_id, error="exhausted retries: RuntimeError"
    )

    row = (
        await session.execute(
            text(
                "SELECT index_status, index_error FROM document_versions WHERE id = :id"
            ),
            {"id": version_id},
        )
    ).mappings().one()
    assert row["index_status"] == "failed"
    assert row["index_error"] == "corrupted: PDFSyntaxError"
