"""Keyed fixture embeddings — content-addressed by `chunk_key(body_text)`.

The on-disk file `embeddings.npz` carries two parallel arrays:

  keys:       (N,) np.bytes_           # blake2b-128 hex digest of body_text
  embeddings: (N, 1024) np.float16

Invariant: `keys[i]` is the hash whose embedding lives at `embeddings[i]`.
Callers never trust positional order — they look up by hash via `lookup`.
"""
from __future__ import annotations

from hashlib import blake2b
from pathlib import Path

import numpy as np

from buscasam.fixtures.corpus import Chunk

EMBEDDINGS_FILE = Path(__file__).parent / "embeddings.npz"


def chunk_key(body_text: str) -> str:
    return blake2b(body_text.encode("utf-8"), digest_size=16).hexdigest()


def load() -> dict[str, np.ndarray]:
    if not EMBEDDINGS_FILE.exists():
        raise FileNotFoundError(
            f"{EMBEDDINGS_FILE} missing — run "
            "`uv run scripts/regenerate_fixture_embeddings.py` with TEI up."
        )
    with np.load(EMBEDDINGS_FILE) as f:
        keys = f["keys"]
        embeddings = f["embeddings"]
    return {k.decode("ascii"): embeddings[i] for i, k in enumerate(keys)}


def lookup(table: dict[str, np.ndarray], chunk: Chunk) -> np.ndarray:
    key = chunk_key(chunk.body_text)
    try:
        return table[key]
    except KeyError as e:
        raise KeyError(
            f"regenerate embeddings.npz: missing embedding for "
            f"chunk_seq={chunk.chunk_seq} doc_id={chunk.doc_id} "
            f"(body_text hash {key})"
        ) from e
