# multilingual-e5-large served by TEI, CPU on-prem

## Status

Accepted

## Decision

`intfloat/multilingual-e5-large` (1024 dim, 512 max tokens, symmetric `query:` / `passage:` prefixes) runs locally inside a Hugging Face Text Embeddings Inference (TEI) sidecar, CPU-only at MVP. Python clients call TEI over HTTP through a single chokepoint module that owns the prefix scheme.

## Locked

1. Model: `intfloat/multilingual-e5-large`, pinned to a specific HF revision SHA. 1024-dim dense embeddings. 512 token context.
2. Runtime: TEI sidecar container, CPU build (`ghcr.io/huggingface/text-embeddings-inference:cpu-…`), pinned by image digest. One TEI instance shared by API and indexer.
3. Prefix chokepoint. A single Python module exposes `embed(text, kind)` and `embed_batch(texts, kind)` with `kind: Literal["query", "passage"]` required (no default). Literals `"query:"` and `"passage:"` appear nowhere else in the codebase; CI grep enforces. Indexer always passes `"passage"`, search API always passes `"query"`.
4. Tokenization. The chunker uses the local `tokenizers` library loaded with the e5 tokenizer file at the same revision SHA as the model. Effective chunk budget: **510 tokens** (512 minus 2 tokens consumed by the `passage: ` prefix). Indexer can chunk without TEI being up.
5. Version pinning, single source of truth. Three identifiers — TEI image digest, HF model revision, local tokenizer file revision — propagated from one config constant (`EMBEDDING_MODEL_REVISION` in `pyproject.toml` / env). Tokenizer file vendored in the repo.
6. Per-row provenance: `chunks.embedding_model_version TEXT NOT NULL`.
7. Headline chunks use the same model and prefix. The `is_headline=true` chunk is embedded with `passage:` like body chunks. "Trabajos relacionados" uses doc-to-doc cosine on headline vectors.
8. Failure mode: degrade to lexical-only. On TEI 5xx or timeout from the search path, the SQL fusion query skips the semantic CTE; RRF tolerates an empty semantic side mathematically. Query-path timeout ~500 ms. Indexer uses a separate, longer timeout with retries. `lexical_fallback_rate` metric logged.
