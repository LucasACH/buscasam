"""TEI chokepoint — owns `query:` / `passage:` prefix, truncation, normalization.

ADR-0002 §3 (single seam to TEI), §8 (degrade-to-lexical on TEI failure).
Module map § `core/embed`.
"""

from __future__ import annotations

import re
from collections import OrderedDict
from typing import Literal

import httpx
import numpy as np

from buscasam.core.tokenizer import vendored_revision
from buscasam.settings import settings

# CPU-only TEI shares a 2-vCPU box; a passage batch can take ~30s under
# contention. Generous ceiling so a slow batch completes rather than raising
# EmbedUnavailable and failing the whole index job (which retries from scratch).
INDEX_TIMEOUT_S = 90.0

# Passage indexing slices into batches of this size. Kept well below TEI's
# max_client_batch_size (router default 32) so each /embed call stays short on
# CPU-only TEI: a smaller payload finishes far under INDEX_TIMEOUT_S, so one slow
# chunk can't push a wide batch over the deadline and fail the whole job.
_MAX_CLIENT_BATCH_SIZE = 8

# Query-embedding cache: assumes a pinned model revision for the process
# lifetime (assert_model_revision_pinned), so identical query text always maps
# to the same vector. A revision change requires a process restart (acceptable).
_QUERY_CACHE_MAX = 1024
_query_cache: OrderedDict[str, np.ndarray] = OrderedDict()


def normalize_query(text: str) -> str:
    """Canonical query normalization (whitespace collapse + casefold).

    Single source of truth: the query-embedding cache key and the search_events
    `q_norm` (core/search_log) must agree so impressions group by the exact unit
    the embedder sees. Don't reimplement — import this.
    """
    return re.sub(r"\s+", " ", text).strip().casefold()


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
    cache_key = normalize_query(text) if kind == "query" else None
    if cache_key is not None and (hit := _query_cache.get(cache_key)) is not None:
        _query_cache.move_to_end(cache_key)
        return hit

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
    vec = np.asarray(r.json()[0], dtype=np.float16)
    if cache_key is not None:
        _query_cache[cache_key] = vec
        if len(_query_cache) > _QUERY_CACHE_MAX:
            _query_cache.popitem(last=False)
    return vec


async def embed_batch(
    client: httpx.AsyncClient,
    texts: list[str],
    *,
    kind: Literal["passage"],
) -> list[np.ndarray]:
    """Embed many passages, slicing into TEI client-batch-sized requests.

    Passage-only (no query cache): indexing embeds each chunk exactly once.
    Same degrade contract as `embed` — EmbedUnavailable on TEI 5xx/timeout so the
    job retries (ADR-0002 §8). Returns vectors aligned 1:1 with `texts`."""
    out: list[np.ndarray] = []
    for start in range(0, len(texts), _MAX_CLIENT_BATCH_SIZE):
        batch = texts[start : start + _MAX_CLIENT_BATCH_SIZE]
        payload = {
            "inputs": [f"{kind}: {t}" for t in batch],
            "truncate": True,
            "normalize": True,
        }
        try:
            r = await client.post("/embed", json=payload, timeout=INDEX_TIMEOUT_S)
            r.raise_for_status()
        except httpx.RequestError as e:
            raise EmbedUnavailable from e
        except httpx.HTTPStatusError as e:
            if e.response.status_code >= 500:
                raise EmbedUnavailable from e
            raise
        out.extend(np.asarray(v, dtype=np.float16) for v in r.json())
    return out
