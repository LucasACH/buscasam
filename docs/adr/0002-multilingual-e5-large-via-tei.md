# multilingual-e5-large served by TEI, CPU on-prem

## Status

Accepted

## Decision

BUSCASAM uses `intfloat/multilingual-e5-large` (1024 dim, 512 max tokens, symmetric with `query:` / `passage:` prefixes) as its embedding model. The model runs locally on UNSAM hardware inside a Hugging Face Text Embeddings Inference (TEI) sidecar container, CPU-only at MVP. Python clients (the search API and the async indexer) call TEI over HTTP through a single chokepoint module that owns the prefix scheme.

## Context

ADR-0001 commits to a single-VM Postgres-only architecture sized around 1024-dim `halfvec` storage with ~512-token chunks. That sizing is only correct if the embedding model produces 1024-dim vectors and consumes inputs that fit within 512 tokens. SPEC also requires a Spanish-optimised pipeline, with other languages indexed by the same model at acceptable (degraded) quality. Hardware is modest on-prem UNSAM infrastructure, the team is small and Python-only, and academic content stays inside the institution.

## Considered options

- **Hosted API (OpenAI `text-embedding-3-large` or `-small`).** Best-in-class quality and zero infra. Rejected: documents would leave UNSAM, dimensionality (3072 / 1536) breaks the storage math in ADR-0001 without Matryoshka truncation, reindex is throttled by API rate limits, and ongoing OPEX has no scaling regime where it wins at this corpus size.
- **`BAAI/bge-m3`.** 1024 dim, 8192 max tokens, newer (2024), strong on multilingual MTEB. Rejected: its 8192-token context is unused (chunks are already small per ADR-0001), and its differentiating sparse + multi-vector outputs are not needed — Postgres `tsvector` already provides the lexical channel. Picking it would pay complexity tax for capabilities the architecture doesn't use.
- **`intfloat/multilingual-e5-large-instruct`.** Marginally better retrieval, same dim. Held in reserve as a drop-in successor if eval shows the base model isn't strong enough on Spanish academic content; same reindex cost as any model swap.
- **Spanish-only models** (e.g., `PlanTL-GOB-ES/*`). Rejected: violates the SPEC clause that other-language documents are still indexed.
- **In-process model loading** in API and indexer workers. Rejected: ~2 GB per worker process. 4 API workers + 1 indexer = ~10 GB on a 16 GB VM also running Postgres + HNSW.
- **Custom FastAPI/Litestar wrapper around `sentence-transformers`.** Strictly worse than TEI unless you need something TEI doesn't support; e5-large is first-class supported.
- **GPU inference.** Rejected for MVP: GPU passthrough requires NVIDIA drivers + `nvidia-container-toolkit` + matching CUDA versions, an ops obligation out of proportion with the actual workload. Reversible — swap the TEI image tag and add `--gpus all` later.

## Architecture decisions locked by this ADR

1. **Model.** `intfloat/multilingual-e5-large`, pinned to a specific Hugging Face revision SHA. 1024-dim dense embeddings. 512 token context (effective budget 510 — see §4).
2. **Runtime.** TEI sidecar container, CPU build (`ghcr.io/huggingface/text-embeddings-inference:cpu-…`), pinned by image digest in `docker-compose.yml`. One TEI instance shared by the search API and the indexer.
3. **Prefix chokepoint.** A single Python module exposes `embed(text, kind)` and `embed_batch(texts, kind)` with `kind: Literal["query", "passage"]` required (no default). The literal strings `"query:"` and `"passage:"` appear nowhere else in the codebase; a CI grep enforces this. The indexer always passes `"passage"`, the search API always passes `"query"`.
4. **Tokenization.** The chunker uses the local `tokenizers` library loaded with the e5 tokenizer file at the same revision SHA as the model. Effective chunk budget is **510 tokens** (512 minus 2 tokens consumed by the `passage: ` prefix). The indexer can chunk a document without TEI being up.
5. **Version pinning, single source of truth.** Three identifiers — TEI image digest, HF model revision, local tokenizer file revision — are propagated from one config constant (e.g., `EMBEDDING_MODEL_REVISION` in `pyproject.toml` / env). The tokenizer file is vendored in the repo so production boot does not depend on Hugging Face being reachable.
6. **Per-row provenance.** `chunks.embedding_model_version TEXT NOT NULL` records the version each embedding was produced with. A reindex updates this column; a startup-time assertion (or CHECK) catches mixed-version corpora.
7. **Headline chunks use the same model and prefix.** The `is_headline=true` chunk (title + abstract per ADR-0001 §3) is embedded with `passage:` like body chunks. "Trabajos relacionados" (ADR-0001 §4) uses doc-to-doc cosine on these headline vectors.
8. **Failure mode: degrade to lexical-only.** On TEI 5xx or timeout from the search path, the SQL fusion query skips the semantic CTE; RRF tolerates an empty semantic side mathematically. Query-path timeout is short (~500 ms, fast-fail). The indexer uses a separate, longer timeout with retries — pending documents wait for TEI to recover. A `lexical_fallback_rate` metric is logged and alerted above baseline.

## Consequences

- **Model swap = reindex + tokenizer swap.** ADR-0001 already names the reindex cost. This ADR adds: the vendored tokenizer file must move in lockstep, and the `chunks.embedding_model_version` column gives the operational handle (reindex updates it row by row; mixed values during cutover are explicit, not silent).
- **Bulk reindex is hours-long on CPU.** ~3 h at MVP corpus size (1M chunks), ~10-12 h at the 5-year horizon (4M chunks). Acceptable as a planned maintenance window; the old index keeps serving until cutover. Moving to GPU collapses this to ~10-30 min — supported by changing the TEI image tag.
- **Prefix discipline is load-bearing.** Mixing `query:` and `passage:` between index and search paths silently costs ~10-20% recall with no error. The chokepoint module is the only thing standing between correctness and a silent quality regression.
- **TEI is on the query critical path.** Outages affect search quality (not availability — see §8 fallback). Routine TEI restarts during model rollouts must complete in seconds, not minutes, or the `lexical_fallback_rate` spikes.
- **One container added to the dev stack.** Local dev requires the TEI container running; the model is downloaded on first start and cached in a Docker volume.
- **RAM budget on the VM.** TEI holds one ~2 GB model copy. Combined with Postgres + HNSW in RAM, the 16 GB VM is comfortably within budget but is the binding constraint — no second model variant can be loaded simultaneously on this hardware without a memory upgrade.
- **Reversible substitutions.** Swapping to `multilingual-e5-large-instruct` or BGE-M3 later is a model-image change, a tokenizer-file swap, and a reindex. The dimensionality (1024) and architecture (TEI sidecar, CPU/GPU swap by image tag) survive any of these substitutions.
