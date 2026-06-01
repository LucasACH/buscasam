"""Calibrate MIN_SEMANTIC_SIMILARITY against the committed Spanish eval set.

Sweeps the semantic floor over the fixture corpus (`fixtures/corpus.py` +
`fixtures/relevance_queries.py`) and reports precision/recall/F1 plus the
false-positive rate on negative queries, then recommends a floor.

The floor only gates *pure-semantic* candidates (lexical hits bypass it), so
this sweeps semantic-only retrieval: a doc is "retrieved" at floor τ when its
best chunk cosine ≥ τ. Candidates are restricted to público-visible docs to
mirror what `core/document_access.invitado_where` would let through.

Requires TEI running with the e5 model (queries are embedded live):

    docker compose --profile tei up -d tei
    uv run scripts/calibrate_floor.py

This is offline calibration tooling (ADR-0001 §12), not a runtime module. The
fixture is synthetic and small — re-run against the real corpus before trusting
the result in production.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from buscasam.fixtures.corpus import CHUNKS, DOCUMENTS  # noqa: E402
from buscasam.fixtures.embeddings import chunk_key, load  # noqa: E402
from buscasam.fixtures.relevance_queries import NEGATIVE, POSITIVE, QUERIES  # noqa: E402
from buscasam.settings import settings  # noqa: E402

TEI_URL = os.environ.get("TEI_URL", "http://localhost:8080")
GRID = np.round(np.arange(0.78, 0.905, 0.005), 3)


def _visible_doc_ids() -> set[int]:
    """público + published + not soft-deleted + not moderation-hidden."""
    return {
        d.id
        for d in DOCUMENTS
        if d.visibility == "publico"
        and d.publication_status == "published"
        and not d.soft_deleted
        and not d.moderation_hidden
    }


def _doc_chunk_embeddings() -> dict[int, list[np.ndarray]]:
    table = load()
    by_doc: dict[int, list[np.ndarray]] = {}
    for c in CHUNKS:
        by_doc.setdefault(c.doc_id, []).append(
            table[chunk_key(c.body_text)].astype(np.float32)
        )
    return by_doc


def _embed_queries(queries: list[str]) -> list[np.ndarray]:
    with httpx.Client(timeout=120) as client:
        r = client.post(
            f"{TEI_URL}/embed",
            json={
                "inputs": [f"query: {q}" for q in queries],
                "normalize": True,
                "truncate": True,
            },
        )
        r.raise_for_status()
        return [np.asarray(v, dtype=np.float32) for v in r.json()]


def _max_sim_per_doc(
    q_vec: np.ndarray, by_doc: dict[int, list[np.ndarray]], visible: set[int]
) -> dict[int, float]:
    return {
        doc_id: max(float(q_vec @ emb) for emb in embs)
        for doc_id, embs in by_doc.items()
        if doc_id in visible
    }


def main() -> None:
    visible = _visible_doc_ids()
    by_doc = _doc_chunk_embeddings()
    q_vecs = _embed_queries([rq.q for rq in QUERIES])
    sims = [_max_sim_per_doc(v, by_doc, visible) for v in q_vecs]

    print(f"corpus: {len(visible)} público-visible docs | "
          f"{len(POSITIVE)} positive + {len(NEGATIVE)} negative queries")
    print(f"current settings.min_semantic_similarity = {settings.min_semantic_similarity}\n")
    print(f"{'floor':>7}{'prec':>8}{'recall':>8}{'F1':>8}{'neg_FP':>9}")
    print("-" * 38)

    best: tuple[float, float | None] = (-1.0, None)  # (f1, floor)
    first_clean_neg: float | None = None
    for tau in GRID:
        tp = fp = fn = 0
        neg_hits = 0
        for rq, sim in zip(QUERIES, sims):
            retrieved = {d for d, s in sim.items() if s >= tau}
            tp += len(retrieved & rq.relevant_doc_ids)
            fp += len(retrieved - rq.relevant_doc_ids)
            fn += len(rq.relevant_doc_ids - retrieved)
            if not rq.relevant_doc_ids and retrieved:
                neg_hits += 1
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        neg_fp = neg_hits / len(NEGATIVE)
        if first_clean_neg is None and neg_hits == 0:
            first_clean_neg = float(tau)
        if f1 > best[0]:
            best = (f1, float(tau))
        marker = " <- current" if abs(tau - settings.min_semantic_similarity) < 1e-9 else ""
        print(f"{tau:7.3f}{prec:8.3f}{rec:8.3f}{f1:8.3f}{neg_fp:9.2f}{marker}")

    print("-" * 38)
    print(f"max-F1 floor:            {best[1]:.3f}  (F1={best[0]:.3f})")
    if first_clean_neg is not None:
        print(f"lowest zero-FP floor:    {first_clean_neg:.3f}  (no negative query leaks)")
    else:
        print("lowest zero-FP floor:    none in grid — negatives leak at every floor")
    print("\nNote: synthetic fixture. Re-run on the real corpus before shipping a value.")


if __name__ == "__main__":
    main()
