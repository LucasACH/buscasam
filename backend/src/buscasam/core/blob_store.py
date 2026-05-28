"""Sole owner of all filesystem IO under BLOB_ROOT (ADR-0006 §3).

Public surface (ADR-0006 §3):
    put_stream, open_for_send, internal_path, local_path, exists,
    discard_if_unreferenced, delete
"""
from __future__ import annotations

import hashlib
import os
import time
import uuid
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import AsyncIterator

import magic
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.settings import settings

BLOB_ROOT: Path = settings.blob_root

_MIME_SNIFF_BYTES = 2048


class BlobTooLarge(Exception):
    pass


@dataclass(frozen=True)
class BlobPutResult:
    sha256: str
    bytes: int
    sniffed_mime: str


def _sharded_path(sha256: str) -> Path:
    return BLOB_ROOT / sha256[:2] / sha256[2:4] / sha256


async def put_stream(
    stream: AsyncIterator[bytes], *, max_bytes: int
) -> BlobPutResult:
    tmp_dir = BLOB_ROOT / ".tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    tmp_path = tmp_dir / f"{uuid.uuid4().hex}.partial"
    hasher = hashlib.sha256()
    total = 0
    mime_buf = b""

    try:
        with tmp_path.open("wb") as fh:
            async for chunk in stream:
                total += len(chunk)
                if total > max_bytes:
                    raise BlobTooLarge(f"upload exceeds {max_bytes} bytes")
                if len(mime_buf) < _MIME_SNIFF_BYTES:
                    mime_buf += chunk
                hasher.update(chunk)
                fh.write(chunk)
            fh.flush()
            os.fsync(fh.fileno())
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    sha256 = hasher.hexdigest()
    sniffed_mime = magic.from_buffer(mime_buf[:_MIME_SNIFF_BYTES], mime=True)
    final = _sharded_path(sha256)

    if final.exists():
        tmp_path.unlink(missing_ok=True)
    else:
        final.parent.mkdir(parents=True, exist_ok=True)
        os.rename(tmp_path, final)

    return BlobPutResult(sha256=sha256, bytes=total, sniffed_mime=sniffed_mime)


async def open_for_send(sha256: str) -> AsyncIterator[bytes]:
    path = _sharded_path(sha256)
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(65536)
            if not chunk:
                break
            yield chunk


def internal_path(sha256: str) -> str:
    return f"/_blobs/{sha256[:2]}/{sha256[2:4]}/{sha256}"


def local_path(sha256: str) -> Path:
    return _sharded_path(sha256)


async def exists(sha256: str) -> bool:
    return _sharded_path(sha256).exists()


async def iter_orphan_candidates(*, min_age: timedelta) -> AsyncIterator[str]:
    """Yield the sha256 of every stored blob whose final-path mtime is older
    than `min_age` (ADR-0006 §12 orphan sweep). Walks the two-level sharded
    tree (ab/cd/abcd…), skipping the `.tmp/` staging dir. The mtime grace is
    the argument, not baked in; reference checking + unlink stay on
    `discard_if_unreferenced`.
    """
    cutoff = time.time() - min_age.total_seconds()
    if not BLOB_ROOT.exists():
        return
    for shard1 in BLOB_ROOT.iterdir():
        if not shard1.is_dir() or shard1.name == ".tmp":
            continue
        for shard2 in shard1.iterdir():
            if not shard2.is_dir():
                continue
            for blob in shard2.iterdir():
                if blob.is_file() and blob.stat().st_mtime < cutoff:
                    yield blob.name


async def discard_if_unreferenced(session: AsyncSession, sha256: str) -> None:
    """Delete the blob iff no row references it. Per-sha form of the §12
    orphan sweep — callers abandoning a content-addressed blob (rejected
    upload, scratch artifact) use this so a dedup hit against a still-
    referenced row stays safe.
    """
    row = (
        await session.execute(
            text(
                "SELECT 1 FROM document_versions "
                "WHERE sha256 = decode(:sha, 'hex') "
                "UNION ALL "
                "SELECT 1 FROM document_attachments "
                "WHERE sha256 = decode(:sha, 'hex') "
                "LIMIT 1"
            ),
            {"sha": sha256},
        )
    ).first()
    if row is None:
        _sharded_path(sha256).unlink(missing_ok=True)


async def delete(sha256: str) -> None:
    """GC entry point (ADR-0006 §3, §12). Application code should call
    `discard_if_unreferenced` instead — only the orphan sweep knows the blob
    is safe to delete unconditionally.
    """
    _sharded_path(sha256).unlink(missing_ok=True)
