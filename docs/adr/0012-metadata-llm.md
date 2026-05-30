# Optional local LLM cleanup of staged metadata, off by default

## Status

Accepted

## Decision

Staged `abstract`/`keywords` suggestions (ADR-0007 §6–7) may be refined by a local, self-hosted LLM before the author reviews them. The LLM is an *optional enhancement layer wrapping the existing heuristics*, not a replacement: `core/extract.derive_metadata` still produces a complete deterministic fallback, and the indexer never depends on the LLM being reachable. The cleanup runs only when `BUSCASAM_METADATA_LLM_ENABLED=1`; any timeout, outage, malformed output, or non-Spanish result degrades silently to the heuristic fallback. The model is served by an Ollama-compatible HTTP endpoint that lives **outside** the single Compose stack — a separate, scale-to-zero GCP Compute Engine GPU VM (`infra/metadata-llm/`) — because GPU inference does not fit the CPU-only application host of ADR-0009. This ADR supersedes ADR-0007's "purely heuristic" framing of §6–7 and documents the `infra/metadata-llm/` stack that ADR-0009's addendum referenced but did not justify.

## Locked

1. Same chokepoint. All LLM logic lives in `core/extract.py`, behind `suggest_metadata(doc, client=None) -> IndexableMetadata`. The indexer (`core/jobs.py`) calls `suggest_metadata`; it never imports `httpx` or talks to the LLM directly. ADR-0007 §1's "all extraction and metadata derivation lives in `core/extract.py`" is unchanged.

2. Heuristic is the floor, not the LLM. `suggest_metadata` first computes `fallback = derive_metadata(doc)`. It returns `fallback` unchanged when `metadata_llm_enabled` is false or the extracted text is empty. The LLM can only refine `abstract` and `keywords`; `fecha` always comes from the heuristic (ADR-0007 §8). An explicit in-document `Resumen/Abstract` heading still wins over the LLM abstract.

3. Non-fatal by construction. A `TimeoutException`, any `HTTPError`, or a `ValueError` from malformed/invalid-schema output is caught, logged as `metadata_llm_failed`, and falls back to the heuristic. Indexing always completes. This mirrors ADR-0002 §8's "degrade gracefully" stance for TEI; the embedding/search path is unaffected since metadata cleanup runs only in the indexer.

4. Spanish enforcement. The output is rejected (fall back to heuristic, log `metadata_llm_non_spanish`) when it trips the Portuguese-marker guard. The prompt mandates Spanish output and forbids Portuguese/English. The pipeline language remains Spanish end to end (SPEC §Idioma, ADR-0001 §8).

5. Transport contract. `core/extract` POSTs to `/api/generate` (Ollama) with `{model, prompt, stream: false, format: <JSON schema>}` and reads `response`. Bounded by `BUSCASAM_METADATA_LLM_TIMEOUT_S` (default 60 s). The prompt sends at most `_LLM_TEXT_CHAR_CAP` (12 000) characters of body text and passes the heuristic output as hints.

6. Configuration. Four `pydantic-settings` fields, all `BUSCASAM_`-prefixed:
   - `metadata_llm_enabled: bool = False`
   - `metadata_llm_url: str` (Ollama base URL)
   - `metadata_llm_model: str` (default `qwen2.5:7b-instruct`)
   - `metadata_llm_timeout_s: float = 60.0`

   `metadata_llm_model` must match the model pulled by the inference host (`infra/metadata-llm/variables.tf:model`). Dev may point `metadata_llm_url` at a local `ollama serve` with a smaller model (`docs/local-dev.md`); the value is operator-chosen, not pinned.

7. Inference host is out-of-stack and scale-to-zero. The model is **not** a Compose service. ADR-0009's "single Docker Compose stack on one VM" still holds for the application: GPU inference would not fit the CPU-only host, so it runs on a separate Spot **NVIDIA L4** GCP Compute Engine VM defined in `infra/metadata-llm/` (Terraform). The VM has no external IP; only the app/worker subnet (`app_source_ranges`) reaches Ollama on `:11434`. Because §3 makes an outage non-fatal, the VM may be scaled to zero (`terraform apply -var running=false`) when the indexing queue is idle. Automated start/stop on queue depth is not in scope; the toggle is a manual operator action at MVP.

8. MVP posture: shipped disabled. `metadata_llm_enabled` defaults to false in code, `.env.example`, and `compose` env. The default deployment is heuristic-only and identical to ADR-0007. Enabling the feature is an explicit operator decision that also requires standing up `infra/metadata-llm/`. The feature is not a launch gate.
