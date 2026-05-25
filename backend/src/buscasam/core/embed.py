"""TEI chokepoint — owns `query:` / `passage:` prefix, truncation, normalization.

ADR-0002 §3 (single seam to TEI), §8 (degrade-to-lexical on TEI failure).
Module map § `core/embed`.
"""
from __future__ import annotations

from typing import Literal

import httpx
import numpy as np

QUERY_TIMEOUT_S = 0.5


class EmbedUnavailable(Exception):
    """Raised when TEI is 5xx or times out — caller substitutes lexical-only."""


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
    try:
        r = await client.post("/embed", json=payload, timeout=QUERY_TIMEOUT_S)
        r.raise_for_status()
    except httpx.RequestError as e:
        raise EmbedUnavailable from e
    except httpx.HTTPStatusError as e:
        if e.response.status_code >= 500:
            raise EmbedUnavailable from e
        raise
    return np.asarray(r.json()[0], dtype=np.float16)
