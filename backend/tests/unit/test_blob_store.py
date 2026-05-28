"""Unit tests for core/blob_store per ADR-0006 §3/§4."""
from __future__ import annotations

import asyncio
import hashlib
import os
import time
from datetime import timedelta
from pathlib import Path

import pytest

from buscasam.core import blob_store


async def _stream(data: bytes):
    yield data


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def blob_root(tmp_path, monkeypatch):
    root = tmp_path / "blobs"
    root.mkdir()
    monkeypatch.setattr(blob_store, "BLOB_ROOT", root)
    return root


async def test_put_stream_atomic_write(blob_root):
    data = b"%PDF-1.4 fake pdf content"
    result = await blob_store.put_stream(_stream(data), max_bytes=1024)

    sha = _sha256(data)
    assert result.sha256 == sha
    assert result.bytes == len(data)

    expected_path = blob_root / sha[:2] / sha[2:4] / sha
    assert expected_path.exists()
    assert expected_path.read_bytes() == data

    tmp_dir = blob_root / ".tmp"
    assert not any(tmp_dir.iterdir()) if tmp_dir.exists() else True


async def test_put_stream_dedup_on_collision(blob_root):
    data = b"duplicate content"
    result1 = await blob_store.put_stream(_stream(data), max_bytes=1024)
    result2 = await blob_store.put_stream(_stream(data), max_bytes=1024)

    assert result1.sha256 == result2.sha256

    tmp_dir = blob_root / ".tmp"
    assert not any(tmp_dir.iterdir()) if tmp_dir.exists() else True

    sha = _sha256(data)
    expected_path = blob_root / sha[:2] / sha[2:4] / sha
    assert expected_path.exists()


async def test_put_stream_exceeds_max_bytes_raises(blob_root):
    data = b"too much data"
    with pytest.raises(blob_store.BlobTooLarge):
        await blob_store.put_stream(_stream(data), max_bytes=5)

    tmp_dir = blob_root / ".tmp"
    assert not any(tmp_dir.iterdir()) if tmp_dir.exists() else True


async def test_put_stream_mime_sniff(blob_root):
    pdf_header = b"%PDF-1.4 " + b"\x00" * 2048
    result = await blob_store.put_stream(_stream(pdf_header), max_bytes=10_000)
    assert result.sniffed_mime == "application/pdf"


async def test_iter_orphan_candidates_skips_tmp_staging_dir(blob_root):
    put = await blob_store.put_stream(_stream(b"stored blob"), max_bytes=1024)
    old = time.time() - 25 * 3600
    os.utime(blob_store.local_path(put.sha256), (old, old))

    tmp = blob_root / ".tmp"
    tmp.mkdir(exist_ok=True)
    partial = tmp / "abcd.partial"
    partial.write_bytes(b"in flight")
    os.utime(partial, (old, old))

    seen = [
        sha
        async for sha in blob_store.iter_orphan_candidates(
            min_age=timedelta(hours=24)
        )
    ]

    assert seen == [put.sha256]
