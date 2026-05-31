# Most-read tracking is a display surface, decoupled from search ranking

## Status

Accepted

## Context

The search landing now shows **más leídos** (most-read this week), which requires
tracking **lecturas** (document detail-page opens) in a new `document_reads` table
(module map `discovery-most-read.md`). Once read counts exist as data, the obvious
next thought is to fold them into search ranking as a popularity signal. SPEC
§Ranking already states "Fusión por Reciprocal Rank Fusion; sin boost por
popularidad o recencia" — but that line predates the existence of any read data, so
this ADR records the decision deliberately, now that the temptation is real.

## Decision

**Lectura** counts feed the **más leídos** display surface only. They do NOT
influence search ranking. `core/search_query` fusion stays pure RRF (semantic +
lexical) with no popularity or recency term. `core/discovery.most_read` reads
`document_reads`; the search retrieval path never does.

## Locked

1. One-way dependency. `core/discovery` (most-read) may read `document_reads`. The
   search retrieval path (`core/search`, `core/search_query`) must not. No popularity
   column, join, or boost term enters the fusion query.

2. Display-only ranking. **Más leídos** is a separate, público-only, shared ranking
   ordered by **lectura** count over a rolling window. It is never blended into the
   `/api/search` result order.

3. Rationale, so this is not re-litigated: search relevance is a quality contract
   (calibrated semantic floor + RRF, ADR-0002); popularity is a feedback loop that
   rewards already-popular documents and starves new ones. Keeping the two surfaces
   separate preserves relevance integrity and matches the SPEC. Revisiting this
   requires a new ADR and a SPEC §Ranking change, not an incremental query edit.

## Consequences

- A future "sort by popularity" or "trending in results" feature is a deliberate ADR
  decision, not a drop-in query tweak.
- `document_reads` has exactly one consumer (`core/discovery`); the search path is
  unaffected by its presence, absence, or staleness.
