# multilingual-e5-large served by TEI, CPU on-prem

## Status

Accepted

## Decision

`intfloat/multilingual-e5-large` (1024 dim, 512 max tokens, required `query:` / `passage:` retrieval prefixes) runs locally inside a Hugging Face Text Embeddings Inference (TEI) sidecar, CPU-only at MVP. Python clients call TEI over HTTP through a single chokepoint module that owns prefixing, truncation, and normalization.

## Locked

1. Model: `intfloat/multilingual-e5-large`, pinned to a specific HF revision SHA. 1024-dim dense embeddings. 512 token context.
2. Runtime: TEI sidecar container, CPU build (`ghcr.io/huggingface/text-embeddings-inference:cpu-…`), pinned by image digest. One TEI instance shared by API and indexer.
3. Prefix chokepoint. `core/embed.py` exposes `embed(text, kind)` and `embed_batch(texts, kind)` with `kind: Literal["query", "passage"]` required (no default). Indexer body/headline retrieval embeddings pass `"passage"`; search queries pass `"query"`. Tests assert feature code uses this API rather than hand-prefixing.
4. Tokenization. The chunker uses the vendored e5 tokenizer at the same revision SHA as the model and measures the full prefixed encoded input, including special tokens. Each `passage` chunk must encode to `<= 512` tokens; no fixed subtraction is assumed. Oversized headline text is truncated through the same measured rule. Indexer can chunk without TEI being up.
5. Version pinning. `EMBEDDING_MODEL_REVISION` is the single source for the HF model and vendored tokenizer revision; startup verifies the tokenizer manifest matches it. The TEI container image digest is a separate dependency pin in Compose because it is not derived from the model revision.
6. Per-row provenance: `chunks.embedding_model_version TEXT NOT NULL`.
7. Headline embeddings. `is_headline=true` stores the normal `passage` embedding for text search plus a `similarity_embedding halfvec(1024)` encoded with `kind="query"` for headline-to-headline related-document cosine. Body chunks have `similarity_embedding IS NULL`. A fixture-based relevance smoke test gates launch.
8. Failure mode: degrade to lexical-only. On TEI 5xx or timeout from the search path, SQL skips the semantic CTE; RRF tolerates an empty semantic side. Query-path timeout starts at 500 ms and is adjusted by the launch benchmark. Indexer uses longer timeouts with retries. `lexical_fallback_rate` is logged. API startup never depends on TEI health.
