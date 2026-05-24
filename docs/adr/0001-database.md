# Postgres as ranked retrieval engine and primary store

## Status

Accepted

## Decision

Single Postgres instance (`pgvector/pgvector:pg16`, pgvector >= 0.8) holds relational data, ranked full-text index, and vector index. Hybrid ranking is a SQL query fusing two CTEs - lexical (`tsvector` + `ts_rank_cd` over a custom `es_unaccent` Spanish config) and semantic (cosine-distance pgvector HNSW with iterative scan) - via Reciprocal Rank Fusion. This is PostgreSQL ranked FTS, not BM25.

## Locked

1. Single `pgvector/pgvector:pg16` container in dev and prod. Backups and recovery point rules are in ADR-0009.
2. Hybrid via RRF in SQL: two CTEs (`lexical_topN`, `semantic_topN`), fused by `1/(k+rank)`, ordered by fused score. No score normalization.
3. Chunked indexing. Body is tokenized under ADR-0002 and split with overlap. A successfully published document always has a synthetic headline chunk (`is_headline = true`, `chunk_seq = 0`) derived from final persisted `title + abstract`, even if body extraction is empty. Embedding and `tsvector` live at chunk level. Search aggregates `chunk_id` to `doc_id` via `MAX(score)` on both candidate sides; winning body chunk is the snippet, falling back to headline text.
4. "Trabajos relacionados" uses headline-only similarity embeddings under ADR-0002 and applies normal readable access from ADR-0010.
5. Semantic metric is cosine distance. Schema/index definition is `embedding halfvec(1024)` plus `CREATE INDEX ... USING hnsw (embedding halfvec_cosine_ops)`. Query ordering uses `embedding <=> :query_embedding`. Embeddings are normalized in the embedding chokepoint before storage/query.
6. HNSW uses iterative scan (`SET LOCAL hnsw.iterative_scan = strict_order`) inside the semantic search transaction. Pin pgvector >= 0.8.
7. Hierarchy via `ltree`: `documents.area_path ltree NOT NULL`, GiST-indexed. Filter at any level with `area_path <@ 'ingenieria'`. Path segments are slugs (`ingenieria_informatica`); display names in flat áreas reference table.
8. Spanish FTS pipeline. Custom text search config `es_unaccent` = `unaccent` + `spanish_stem`, applied symmetrically at index and query. No synonyms.
9. Visibility, publication state, deletion, moderation hiding, and accepted authorship are applied before candidate ranking through `core/document_access.py` using ADR-0010's readable predicate. The same predicate protects all document-derived reads, not only search.
10. Generated `tsvector`: `body_tsv tsvector GENERATED ALWAYS AS (to_tsvector('es_unaccent', body_text)) STORED` on `chunks`.
11. Pagination caps relevance results at top 200 fused. Fetch top 200 readable/filter-matching documents from each CTE, RRF, take top 200, paginate 10 per page (max page 20). "Más recientes" bypasses the relevance cap and uses the same access predicate with a matching partial btree index.
12. Relevance floor: candidate is displayed when it has a lexical hit or its best semantic cosine similarity meets a launch-calibrated `MIN_SEMANTIC_SIMILARITY` setting. Calibration fixture and selected value are committed before launch. Below-floor candidates are not results.
13. Relevance result count is computed from the capped fused set and displayed as exact only below 200; a saturated set displays `200+`. "Más recientes" may compute an exact readable/filter-matching count. "Sin resultados" is implementable without a full-corpus semantic count.
