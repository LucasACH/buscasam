"""Spanish relevance eval set for MIN_SEMANTIC_SIMILARITY calibration (ADR-0001 §12).

Labels queries against the committed fixture corpus (`fixtures/corpus.py`):

  - POSITIVE queries map to the público doc_ids that *should* surface.
  - NEGATIVE queries are off-topic / gibberish and should surface nothing — the
    "sé decir que no encontré nada" case the floor exists to protect.

`scripts/calibrate_floor.py` sweeps the floor against this set and reports
precision/recall/F1. This is a SEED set over synthetic fixtures: re-label and
expand it against the real corpus before trusting the calibrated value in prod.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RelevanceQuery:
    q: str
    # público doc_ids that should rank as results; empty => expect "nothing found".
    relevant_doc_ids: frozenset[int] = field(default_factory=frozenset)


# doc_ids 1 and 2 are both about hybrid/dense academic search — either query may
# legitimately surface both, so they share a label to avoid penalising a correct
# topical neighbour as a false positive.
POSITIVE: tuple[RelevanceQuery, ...] = (
    RelevanceQuery(
        "búsqueda híbrida léxico-semántica en repositorios académicos",
        frozenset({1, 2}),
    ),
    RelevanceQuery(
        "recuperación densa con embeddings multilingües en español", frozenset({1, 2})
    ),
    RelevanceQuery("árboles de decisión y el algoritmo ID3", frozenset({3})),
    RelevanceQuery("lógica modal y semántica de mundos posibles", frozenset({4})),
    RelevanceQuery("estructura de la novela argentina del siglo XX", frozenset({5})),
    RelevanceQuery("visualización de embeddings con proyecciones UMAP", frozenset({6})),
    RelevanceQuery(
        "complejidad de los algoritmos de ordenamiento quicksort y mergesort",
        frozenset({7}),
    ),
    RelevanceQuery("deserción y notas en el curso de lógica", frozenset({8})),
    RelevanceQuery("reglamento de la escuela de ciencia y tecnología", frozenset({14})),
    RelevanceQuery("plan de estudios de la licenciatura en filosofía", frozenset({15})),
)

NEGATIVE: tuple[RelevanceQuery, ...] = (
    RelevanceQuery("recetas de cocina italiana caseras"),
    RelevanceQuery("resultados del mundial de fútbol"),
    RelevanceQuery("cómo cambiar el aceite del coche"),
    RelevanceQuery("pronóstico del clima para mañana"),
    RelevanceQuery("qwertzuiop asdfghjkl"),
)

QUERIES: tuple[RelevanceQuery, ...] = POSITIVE + NEGATIVE
