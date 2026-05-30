"""TEI chokepoint — owns `query:` / `passage:` prefix, truncation, normalization.

ADR-0002 §3 (single seam to TEI), §8 (degrade-to-lexical on TEI failure).
Module map § `core/embed`.
"""
from __future__ import annotations

from typing import Literal

import httpx
import numpy as np

from buscasam.core.tokenizer import vendored_revision
from buscasam.settings import settings

INDEX_TIMEOUT_S = 30.0


class EmbedUnavailable(Exception):
    """Raised when TEI is 5xx or times out — caller substitutes lexical-only."""


def halfvec_literal(embedding: np.ndarray) -> str:
    """Serialize a 1024-dim embedding as a pgvector `halfvec` SQL literal (ADR-0001 §5)."""
    return "[" + ",".join(f"{float(v):.6f}" for v in embedding) + "]"


def assert_model_revision_pinned() -> None:
    """ADR-0002 §5: refuse to start if the vendored tokenizer revision disagrees
    with the configured model revision."""
    vendored = vendored_revision()
    if vendored != settings.embedding_model_revision:
        raise RuntimeError(
            "Vendored e5 tokenizer revision "
            f"{vendored!r} != EMBEDDING_MODEL_REVISION "
            f"{settings.embedding_model_revision!r}; the tokenizer used for "
            "chunking is out of sync with the served model."
        )


async def embed(
    client: httpx.AsyncClient,
    text: str,
    *,
    kind: Literal["query", "passage"],
) -> np.ndarray:
    payload = {
        "inputs": [f"{kind}: {text}"],
        "truncate": True,
        "normalize": True,
    }
    timeout = settings.embed_query_timeout_s if kind == "query" else INDEX_TIMEOUT_S
    try:
        r = await client.post("/embed", json=payload, timeout=timeout)
        r.raise_for_status()
    except httpx.RequestError as e:
        raise EmbedUnavailable from e
    except httpx.HTTPStatusError as e:
        if e.response.status_code >= 500:
            raise EmbedUnavailable from e
        raise
    return np.asarray(r.json()[0], dtype=np.float16)
