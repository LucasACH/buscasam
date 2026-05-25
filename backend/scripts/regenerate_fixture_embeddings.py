"""Regenerate `embeddings.npz` for the fixture corpus.

Requires TEI running with the e5 model:

    docker compose --profile tei up -d tei

Then:

    uv run scripts/regenerate_fixture_embeddings.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from buscasam.fixtures.corpus import CHUNKS  # noqa: E402
from buscasam.fixtures.embeddings import EMBEDDINGS_FILE, chunk_key  # noqa: E402

TEI_URL = "http://localhost:8080"


def _wait_for_tei(timeout_s: int = 600) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"{TEI_URL}/health", timeout=2)
            if r.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(2)
    raise RuntimeError(f"TEI not healthy after {timeout_s}s")


def _tei_revision() -> str:
    """Return `model_id@sha` from TEI's `/info` for the fixture's provenance tag.

    ADR-0002 §5 designates EMBEDDING_MODEL_REVISION as the single source for
    the HF model and tokenizer revision. Capture it here when regenerating so
    `chunks.embedding_model_version` traces back to a specific TEI run.
    """
    info = httpx.get(f"{TEI_URL}/info", timeout=5).json()
    model = info.get("model_id", "unknown")
    sha = info.get("model_sha") or info.get("model_revision", "unknown")
    return f"{model}@{sha}"


def main() -> None:
    _wait_for_tei()
    print(f"TEI revision: {_tei_revision()} (paste into corpus.EMBEDDING_MODEL_VERSION)")
    texts = [f"passage: {c.body_text}" for c in CHUNKS]
    with httpx.Client(timeout=120) as client:
        r = client.post(
            f"{TEI_URL}/embed",
            json={"inputs": texts, "normalize": True, "truncate": True},
        )
        r.raise_for_status()
        embeddings = np.asarray(r.json(), dtype=np.float16)

    if embeddings.shape != (len(CHUNKS), 1024):
        raise RuntimeError(f"unexpected TEI shape {embeddings.shape}")

    keys = np.array([chunk_key(c.body_text) for c in CHUNKS], dtype="S32")
    np.savez(EMBEDDINGS_FILE, keys=keys, embeddings=embeddings)
    print(f"wrote {EMBEDDINGS_FILE} shape={embeddings.shape}")


if __name__ == "__main__":
    main()
