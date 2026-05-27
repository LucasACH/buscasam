"""Tests for `blob_store.discard_if_unreferenced` (ADR-0006 §3).

The helper is the caller-facing cleanup for content-addressed blobs: it must
delete only when no `document_versions` or `document_attachments` row points
at the sha, so a dedup hit cannot orphan another row's blob.
"""
from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import text

from buscasam.core import blob_store
from tests.factories import make_document, make_user


@pytest.fixture
def blob_root(tmp_path, monkeypatch):
    root = tmp_path / "blobs"
    root.mkdir()
    monkeypatch.setattr(blob_store, "BLOB_ROOT", root)
    return root


async def _stream(data: bytes):
    yield data


async def test_discard_removes_blob_when_no_row_references_it(session, blob_root):
    put = await blob_store.put_stream(_stream(b"orphan bytes"), max_bytes=1024)

    await blob_store.discard_if_unreferenced(session, put.sha256)

    assert await blob_store.exists(put.sha256) is False


async def test_discard_keeps_blob_when_a_version_row_references_it(
    session, blob_root
):
    payload = b"shared bytes"
    put = await blob_store.put_stream(_stream(payload), max_bytes=1024)

    uid = await make_user(session)
    doc_id = await make_document(session, publication_status="draft", titulo="t")
    await session.execute(
        text(
            "INSERT INTO document_versions "
            "(doc_id, version_no, sha256, original_filename, bytes, mime, uploaded_by) "
            "VALUES (:d, 1, decode(:sha, 'hex'), 'f.pdf', :b, 'application/pdf', :u)"
        ),
        {"d": doc_id, "sha": put.sha256, "b": len(payload), "u": uid},
    )

    await blob_store.discard_if_unreferenced(session, put.sha256)

    assert await blob_store.exists(put.sha256) is True


async def test_discard_keeps_blob_when_an_attachment_row_references_it(
    session, blob_root
):
    payload = b"shared attachment bytes"
    put = await blob_store.put_stream(_stream(payload), max_bytes=1024)

    uid = await make_user(session)
    doc_id = await make_document(session, publication_status="draft", titulo="t")
    await session.execute(
        text(
            "INSERT INTO document_attachments "
            "(doc_id, sha256, original_filename, bytes, mime, uploaded_by) "
            "VALUES (:d, decode(:sha, 'hex'), 'a.csv', :b, 'text/csv', :u)"
        ),
        {"d": doc_id, "sha": put.sha256, "b": len(payload), "u": uid},
    )

    await blob_store.discard_if_unreferenced(session, put.sha256)

    assert await blob_store.exists(put.sha256) is True


async def test_discard_is_no_op_for_unknown_sha(session, blob_root):
    sha = hashlib.sha256(b"never written").hexdigest()

    await blob_store.discard_if_unreferenced(session, sha)

    assert await blob_store.exists(sha) is False
