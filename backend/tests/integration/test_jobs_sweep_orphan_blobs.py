"""Tests for the orphan-blob sweep core (`jobs._run_sweep_orphan_blobs`).

Module map §core/jobs + §core/blob_store: the sweep drives
`blob_store.iter_orphan_candidates(min_age=24h)` into the existing per-sha
`discard_if_unreferenced`. It reclaims blobs no live `document_versions` /
`document_attachments` row references, skips still-referenced shas, honors the
24h mtime grace, and is idempotent (ADR-0006 §12).
"""
from __future__ import annotations

import os
import time

import pytest
from sqlalchemy import text

from buscasam.core import blob_store, jobs
from tests.factories import make_document, make_user


@pytest.fixture
def blob_root(tmp_path, monkeypatch):
    root = tmp_path / "blobs"
    root.mkdir()
    monkeypatch.setattr(blob_store, "BLOB_ROOT", root)
    return root


async def _stream(data: bytes):
    yield data


def _age_blob(sha256: str, *, hours: float) -> None:
    path = blob_store.local_path(sha256)
    past = time.time() - hours * 3600
    os.utime(path, (past, past))


async def test_sweep_deletes_unreferenced_past_grace_blob(session, blob_root):
    put = await blob_store.put_stream(_stream(b"orphan"), max_bytes=1024)
    _age_blob(put.sha256, hours=25)

    await jobs._run_sweep_orphan_blobs(session)

    assert await blob_store.exists(put.sha256) is False


async def test_sweep_skips_sha_referenced_by_live_row(session, blob_root):
    put = await blob_store.put_stream(_stream(b"shared"), max_bytes=1024)
    _age_blob(put.sha256, hours=25)

    uid = await make_user(session)
    doc_id = await make_document(session)
    await session.execute(
        text(
            "INSERT INTO document_versions "
            "(doc_id, version_no, sha256, original_filename, bytes, mime, "
            " uploaded_by) "
            "VALUES (:d, 1, decode(:sha, 'hex'), 'f.pdf', 1, "
            "        'application/pdf', :u)"
        ),
        {"d": doc_id, "sha": put.sha256, "u": uid},
    )

    await jobs._run_sweep_orphan_blobs(session)

    assert await blob_store.exists(put.sha256) is True


async def test_sweep_is_idempotent_across_repeated_runs(session, blob_root):
    put = await blob_store.put_stream(_stream(b"orphan"), max_bytes=1024)
    _age_blob(put.sha256, hours=25)

    await jobs._run_sweep_orphan_blobs(session)
    # Second run finds the blob already gone — unlink missing_ok, no error.
    second = await jobs._run_sweep_orphan_blobs(session)

    assert await blob_store.exists(put.sha256) is False
    assert second == 0


async def test_sweep_honors_mtime_grace_for_young_blob(session, blob_root):
    put = await blob_store.put_stream(_stream(b"fresh upload"), max_bytes=1024)
    _age_blob(put.sha256, hours=1)

    await jobs._run_sweep_orphan_blobs(session)

    assert await blob_store.exists(put.sha256) is True
