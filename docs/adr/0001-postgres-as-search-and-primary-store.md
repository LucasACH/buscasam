# Postgres as both search engine and primary store

## Status

Accepted

## Decision

BUSCASAM runs on a single Postgres instance (`pgvector/pgvector:pg16`, pgvector ≥ 0.8) holding relational data, lexical index, and vector index. No separate search cluster (OpenSearch / Elasticsearch). Hybrid ranking is implemented as a SQL query that fuses two CTEs — lexical (`tsvector` + `ts_rank_cd` over a custom `es_unaccent` Spanish configuration) and semantic (pgvector HNSW with iterative scan) — using Reciprocal Rank Fusion. Sized for <50k docs at MVP and ~200k at a 5-year horizon.

## Context

The SPEC requires hybrid semantic + lexical ranking in Spanish, structured filters (fecha, área jerárquica, tipo), three-tier visibility (público / interno / privado), stable paginated URLs, and a "más recientes" sort. The team is small, the corpus is bounded by one university's academic production, and production runs on modest on-prem UNSAM hardware. A dedicated search engine would be the conventional answer but is poorly matched to the team size and operational budget.

## Considered options

- **OpenSearch / Elasticsearch + Postgres**: native BM25, mature analyzers, well-known. Rejected: a second stateful service to operate, deploy, back up, and sync. The features that would justify it (massive corpus, complex relevance tuning, advanced analyzers) are not in scope.
- **Postgres + pgvector + paradedb/pg_search**: real BM25 inside Postgres via an extension. Rejected: paradedb is the youngest piece of infra in the stack (v0.x), and `ts_rank_cd` is fully sufficient at this corpus size — the BM25-vs-ts_rank distinction is invisible to users at <200k docs and gets washed further by RRF fusion.
- **Postgres + pgvector + native FTS** (chosen): one system, one query language, no second service. `ts_rank_cd` instead of BM25; SPEC wording relaxed accordingly.

## Architecture decisions locked by this ADR

1. **One system.** Single `pgvector/pgvector:pg16` container in dev and prod. Single VM in prod, daily `pg_dump`.
2. **Hybrid via RRF in SQL.** Two CTEs (`lexical_topN`, `semantic_topN`), fused by `1/(k+rank)`, ordered by fused score. No score normalization.
3. **Chunked indexing.** Body split into ~512-token chunks with overlap; `title + abstract` stored as a synthetic headline chunk (`is_headline = true`, `chunk_seq = 0`). Both the embedding and the `tsvector` live at the chunk level. Search aggregates `chunk_id` → `doc_id` via `MAX(score)` symmetrically on both sides; the winning chunk *is* the snippet shown in results.
4. **"Trabajos relacionados" uses the headline embedding** only — keeps doc-to-doc similarity at doc granularity.
5. **HNSW with iterative scan** (`hnsw.iterative_scan = strict_order`). Pin pgvector ≥ 0.8 in `docker-compose`. Necessary because every search filters (visibility is always applied) and classical HNSW post-filtering can return empty result sets on selective filters.
6. **`halfvec` storage** for embeddings (2 bytes/dim). At 1024 dims, 200k docs × ~20 chunks ≈ 8 GB raw vectors plus ~30% HNSW overhead. Comfortable on 16 GB RAM.
7. **Hierarchy via `ltree`.** `docs.area_path ltree NOT NULL`, GiST-indexed. Filter at any level with `area_path <@ 'ingenieria'`. Path segments are slugs (`ingenieria_informatica`); display names live in a flat áreas reference table.
8. **Spanish FTS pipeline.** Custom text search config `es_unaccent` = `unaccent` + `spanish_stem`, applied symmetrically at index and query. No custom synonyms at launch — embeddings absorb semantic variance; SPEC explicitly forbids query expansion.
9. **Visibility enforced in SQL, not RLS.** A central `build_search_query(user_ctx, filters)` builder produces the `WHERE visibility = 'publico' OR (visibility = 'interno' AND :is_unsam) OR (:user_id = ANY(authors))` predicate. Soft-delete piggybacks (`AND NOT soft_deleted`). Partial indexes on `WHERE NOT soft_deleted` keep the search graph clean.
10. **Generated `tsvector`.** `body_tsv tsvector GENERATED ALWAYS AS (to_tsvector('es_unaccent', body_text)) STORED` on `chunks`. Postgres maintains it on write.
11. **Pagination caps at top-200 fused.** Fetch top 200 from each CTE, RRF, take top 200, paginate 10 per page (max page 20). "Más recientes" sort bypasses the cap (pure `ORDER BY fecha DESC` with btree index).
12. **Result count is the exact filter-matching set**, computed separately from ranking. UI shows e.g. "1.247 resultados — mostrando los 200 más relevantes" when the corpus has more matches than the ranking window.

## Consequences

- **Operational simplicity.** One stateful service, one backup story, one ops runbook. No dual-write consistency between Postgres and a search cluster.
- **Pagination ceiling at page 20.** A user paging past result 200 hits "afiná tu búsqueda". Acceptable trade — long-tail semantic results are mostly noise, and Google Scholar caps similarly.
- **Occasional ranking truncation.** A document outside both top-200 candidate windows can't surface even if RRF would have placed it in the top 200. Rare at this corpus size, documented limitation.
- **Spanish accent handling depends on a custom text search configuration.** Every new environment must run the `CREATE EXTENSION unaccent; CREATE TEXT SEARCH CONFIGURATION es_unaccent ...` migration. If skipped, the lexical side silently loses recall on un-accented queries.
- **Embeddings consistency depends on the indexing job.** Postgres maintains `tsvector` automatically (generated column); embeddings come from the model and are written by the async indexing job. A model swap requires a corpus reindex, not a schema change.
- **Scale ceiling.** This shape works to roughly 1M docs / 20M chunks on the same VM with vertical scaling. Beyond that, revisit: move embeddings to a dedicated index (separate Postgres, or a vector DB), or split read replicas. Out of scope for this ADR.
