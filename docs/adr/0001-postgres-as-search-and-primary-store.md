# Postgres as both search engine and primary store

## Status

Accepted

## Decision

Single Postgres instance (`pgvector/pgvector:pg16`, pgvector ≥ 0.8) holds relational data, lexical index, and vector index. Hybrid ranking is a SQL query fusing two CTEs — lexical (`tsvector` + `ts_rank_cd` over a custom `es_unaccent` Spanish config) and semantic (pgvector HNSW with iterative scan) — via Reciprocal Rank Fusion.

## Locked

1. Single `pgvector/pgvector:pg16` container in dev and prod. Daily `pg_dump`.
2. Hybrid via RRF in SQL: two CTEs (`lexical_topN`, `semantic_topN`), fused by `1/(k+rank)`, ordered by fused score. No score normalization.
3. Chunked indexing. Body split into ~512-token chunks with overlap. `title + abstract` stored as a synthetic headline chunk (`is_headline = true`, `chunk_seq = 0`). Embedding and `tsvector` live at the chunk level. Search aggregates `chunk_id` → `doc_id` via `MAX(score)` symmetrically on both sides; winning chunk is the snippet.
4. "Trabajos relacionados" uses the headline embedding only.
5. HNSW with iterative scan (`hnsw.iterative_scan = strict_order`). Pin pgvector ≥ 0.8.
6. `halfvec` storage (2 bytes/dim, 1024 dims).
7. Hierarchy via `ltree`: `documents.area_path ltree NOT NULL`, GiST-indexed. Filter at any level with `area_path <@ 'ingenieria'`. Path segments are slugs (`ingenieria_informatica`); display names in flat áreas reference table.
8. Spanish FTS pipeline. Custom text search config `es_unaccent` = `unaccent` + `spanish_stem`, applied symmetrically at index and query. No synonyms.
9. Visibility enforced in SQL via central `build_search_query(user_ctx, filters)` builder producing `WHERE visibility = 'publico' OR (visibility = 'interno' AND :is_unsam) OR EXISTS (SELECT 1 FROM document_authors da WHERE da.doc_id = documents.id AND da.user_id = :user_id)`. Authorship modeled as `document_authors` join table. Soft-delete: `AND soft_deleted_at IS NULL`. Partial indexes `WHERE soft_deleted_at IS NULL`.
10. Generated `tsvector`: `body_tsv tsvector GENERATED ALWAYS AS (to_tsvector('es_unaccent', body_text)) STORED` on `chunks`.
11. Pagination caps at top-200 fused. Fetch top 200 from each CTE, RRF, take top 200, paginate 10 per page (max page 20). "Más recientes" sort bypasses the cap (`ORDER BY fecha DESC` with btree partial index `WHERE soft_deleted_at IS NULL`).
12. Result count is the exact filter-matching set, computed separately from ranking.
