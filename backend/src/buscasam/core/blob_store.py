"""Sole owner of all filesystem IO under BLOB_ROOT (ADR-0006 §3).

Public surface (ADR-0006 §3):
    put_stream, open_for_send, internal_path, exists, delete
"""
from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator

import magic

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


async def exists(sha256: str) -> bool:
    return _sharded_path(sha256).exists()


async def delete(sha256: str) -> None:
    _sharded_path(sha256).unlink(missing_ok=True)
