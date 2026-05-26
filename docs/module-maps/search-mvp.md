# Module Map: Search MVP (público corpus for invitado users)

## Source

PRD: [Issue #1 — Search MVP: público corpus for invitado users](https://github.com/LucasACH/buscasam/issues/1).

Implements the `/buscar` slice end-to-end: URL-driven hybrid search over the público corpus, área/tipo/fecha filters, relevance vs. más-recientes ordering, lexical fallback when TEI is down.

## Modules

### `core/search_query`

**Interface:** `search.run(filters, user_ctx, embedding: halfvec | None) -> Results` (ADR-0003 §3). Inputs: validated filters (q, area_path or None, tipo[], desde, hasta, orden, pagina), the requester's `UserCtx` (invitado at PRD-1), and an optional query embedding. Calls `document_access.invitado_where("d")` itself — the access predicate does not cross the module boundary as a parameter. Returns `Results { rows: list[ResultRow], total: int }` where each row carries `doc_id, titulo, autores, fecha, area_path, tipo, abstract, snippet`. Invariants: 10 rows per page; `pagina` capped at 20 under `orden=relevancia`; uncapped under `orden=recientes`; `embedding=None` ⇒ lexical-only (RRF tolerates empty semantic side); below-`MIN_SEMANTIC_SIMILARITY` rows excluded unless they have a lexical hit; `total` is `200+` when the fused set saturates under relevance, exact under recientes. Errors: SQLAlchemy/asyncpg errors propagate; no business exceptions.

**Responsibilities:** Hybrid SQL — lexical CTE (`es_unaccent`, `ts_rank_cd`, `ts_headline` for snippet), semantic CTE (pgvector cosine, HNSW iterative scan), RRF fusion, chunk→doc aggregation via `MAX(score)`, top-200 cap, área (`ltree <@`), tipo (`IN`), fecha (year range), `orden=recientes` partial-btree path. Owns snippet generation: `ts_headline` on lexical rows, `LEFT(abstract, 200)` for pure-semantic rows. Truncation of abstract to ~280 chars happens here.

**Internal seams:** `_lexical_candidates_ctes(where, filter_clauses, cap)` produces the `lex_scored`/`lex_best`/`lex_ranked` CTE chain (best-matching chunk per readable doc, optional top-N cap) used identically by `_run_recientes`, `_run_lexical`, and the lex side of `_run_hybrid`. `_headline_expr(body_col)` produces the `ts_headline` SQL expression. These are private to the module — the external interface is unchanged.

**Seams:** None in PRD-1 scope at the external interface. The access fragment is a parameter, not an adapter (no second implementation exists yet — only `document_access.invitado_fragment()`). Score normalization is locked at RRF only.

**Depth note:** Owns every SQL detail of ranked retrieval. Without it, RRF, the iterative-scan setting, the chunk-aggregation rule, the headline-vs-body snippet fallback, and the access fragment would scatter across endpoints. Deletion test: callers would each rewrite ~150 lines of SQL with subtly different semantics. ADR-0001 + ADR-0003 §3 lock this depth.

---

### `core/document_access`

**Interface:** `invitado_where(alias: str) -> str`. Returns a `WHERE`-clause body restricted to the invitado branch, column-qualified under the caller-supplied `alias` for the `documents` table: `<alias>.visibility='publico' AND <alias>.publication_status='published' AND <alias>.soft_deleted_at IS NULL AND <alias>.moderation_hidden_at IS NULL`. The alias is required (not defaulted) so this module owns column qualification at every call site. No user context required at MVP since PRD-1 only ships the invitado branch. (PRD-2 will add `readable_where(alias, user_ctx) -> (str, dict)` covering interno/privado/co-author paths — bind params arrive then.)

**Responsibilities:** Sole owner of "what counts as a readable document." Visibility, publication state, soft-delete, moderation-hidden are joined into one fragment so search, recientes ordering, future detail, related, and sitemap reuse identical semantics.

**Seams:** Conceptual seam on visibility role (invitado / autenticated UNSAM / owner-or-coauthor) but only one adapter exists at PRD-1 — no real seam yet. PRD-2 makes it real.

**Alignment invariant:** Migration 0007's `documents_publico_recientes` partial index has the same predicate text. Postgres' predicate-implication check is textual; drift silently disables the index. Guarded by `tests/integration/test_indices.py::test_invitado_predicate_matches_partial_index_where`, which reads `pg_get_expr(indpred, indrelid)` and compares (normalised for whitespace, `::text` casts, parens) to `invitado_where("documents")`. Future migrations touching this index should construct the WHERE from `invitado_where`.

**Depth note:** A central security predicate. The deletion test is hard: every leak in the MVP would trace back to this module. ADR-0010 §6 locks it as the chokepoint for every document-derived read.

---

### `core/embed`

**Interface:** `embed(text: str, kind: Literal["query", "passage"]) -> halfvec(1024)`. PRD-1 calls with `kind="query"`. Owns the `query:` prefix, tokenizer truncation, L2 normalization, the app-scoped `httpx.AsyncClient` against TEI, and a 500 ms timeout. Raises `EmbedUnavailable` on TEI 5xx or timeout — the search route catches and substitutes `embedding=None`.

**Responsibilities:** Single seam to the TEI sidecar. Owns prefix discipline, revision-pinned tokenizer, normalization, and the timeout policy.

**Seams:** None. Switching embedding backends is out of MVP scope.

**Depth note:** ADR-0002 §3 locks this as the only place feature code talks to TEI. Without it, retrieval prefixes and normalization drift between indexer and search.

---

### `core/search`

**Interface:** `search.execute(session, tei, *, filters, user_ctx, min_semantic_similarity) -> ExecuteResult`. Inputs: validated `Filters`, the requester's `UserCtx`, the TEI client, and the calibrated semantic floor. Returns `ExecuteResult { rows, total, saturated, unfiltered_total: int | None, lexical_fallback: bool }`. Invariants: `unfiltered_total` is populated iff any filter is active and is computed under the same `user_ctx` and `embedding` as the primary call; `lexical_fallback` is always `False` under `orden=recientes` (no embedding requested).

**Responsibilities:** Sole owner of the silent lexical-fallback policy (ADR-0002 §8: catch `EmbedUnavailable`, substitute `embedding=None`, log `lexical_fallback_rate`); sole owner of the "second call with filters dropped" rule for `unfiltered_total`; chooses whether to embed at all (skipped under `orden=recientes`).

**Seams:** Embedder is concrete (`core.embed`) — no adapter at MVP. The retrieval adapter is `core.search_query.run` (single implementation).

**Depth note:** Sits between router and `search_query`. Deletion test: the three policies (fallback, unfiltered double-call, embed-skip on recientes) would each leak into the router and have to be re-pasted into every future authenticated route (PRD-2 onward). The route shrinks to validation + DTO shaping — both URL-shape concerns it correctly owns.

---

### `api/search` (FastAPI router)

**Interface:** `GET /api/search?q=&area=&tipo=&tipo=&desde=&hasta=&orden=&pagina=`. Returns `{results: ResultDTO[], total: int, saturated: bool, unfiltered_total: int | null, lexical_fallback: bool}`. Validates `q` empty ↔ `orden=recientes` (rejects `orden=relevancia` with empty q). Validates `pagina ≤ 20` under relevance. Validates `desde ≤ hasta`.

**Responsibilities:** URL-param → Pydantic Query validation; constructs `Filters` and the invitado `UserCtx`; calls `search.execute(...)`; shapes ORM-free `ResultDTO`s onto `SearchResponse`. Orchestration (embed/fallback, unfiltered double-call, telemetry) lives in `core/search`.

**Seams:** None.

**Depth note:** Thin by design now — pure HTTP edge. Deletion test for the route alone: trivial. Deletion test for the route + `core/search` together: the policy bundle reappears in every future search-style endpoint.

---

### `api/areas` (FastAPI router)

**Interface:** `GET /api/areas`. Returns the full áreas tree as nested `{escuela, carrera[], materia[]}` records or a flat list with `area_path` slugs. Cacheable client-side (no auth, no per-user data).

**Responsibilities:** One SELECT over the áreas reference table, shaped for the cascader.

**Seams:** None.

**Depth note:** Thin by design — earns its own router file because the áreas table is a domain noun and a future detail page may consume it too. If a second non-search caller never materializes by PRD-4, fold it into `api/search`. ADR-0001 §7 locks the áreas table shape.

---

### `app/buscar/page.tsx` (Next.js client page)

**Interface:** Renders at `/buscar`. Reads URL state via `useSearchParams` (q, area, tipo[], desde, hasta, orden, pagina). Composes `SearchFilters`, the result list (inline mapping over `ResultCard`), pagination + sort toggle + page-20 nudge, and `EmptyState`. No SSR (ADR-0004 §3).

**Responsibilities:** Sole owner of URL ↔ component-tree binding. Routes URL updates through `router.replace` so back/forward preserves history. Decides when to render `EmptyState` (results empty) vs. result list.

**Seams:** None.

**Depth note:** The single concentration point for URL contract on the frontend. Deletion test: URL parsing would scatter into every child component.

---

### `app/buscar/useSearch.ts` (hook)

**Interface:** `useSearch(params: SearchParams) -> { data, isLoading, isError, isLexicalFallback }`. Owns the query key (stable across param permutations), the URL-params → `/api/search` request mapping, and exposes whether the backend served a lexical-only response (for telemetry — no UI banner per PRD §"Lexical-fallback UX: silent").

**Responsibilities:** TanStack Query wrapper. Cache key derivation. Request DTO assembly.

**Seams:** None.

**Depth note:** Keeps `page.tsx` a layout. Without it, the page would inline request shaping + query-key construction, making the page hard to test. Deletion test passes once: one caller, but the page's testability hinges on this isolation.

---

### `app/buscar/SearchFilters.tsx`

**Interface:** Controlled by RHF + Zod (ADR-0004 §8). Props: `{ value, onChange }`. Emits a validated filter object on debounced commit. Owns the form schema for área (single `area_path` or null), tipo (multi-select from the 8 closed enum values), desde/hasta (year, 4 digits, optional).

**Responsibilities:** Form binding. Composes `AreasCascader` and the tipo multi-select. Per-filter clear (PRD §21).

**Seams:** None.

**Depth note:** Concentrates form validation. Tipo and orden enums are domain-locked (PRD "Further Notes"), so the validator catches any drift at compile/runtime.

---

### `app/buscar/AreasCascader.tsx`

**Interface:** Props: `{ value: area_path | null, onChange }`. Loads the full áreas tree once via TanStack Query against `/api/areas` (PRD §28: single request). 3-level picker Escuela → Carrera → Materia.

**Responsibilities:** Tree state (selected level + value), reset on parent change, mobile-friendly layout.

**Seams:** None.

**Depth note:** Reusable widget. Deep test: keyboard navigation, partial selection (only Escuela), reset on parent.

---

### `app/buscar/ResultCard.tsx`

**Interface:** Props: `{ result: ResultDTO }`. Pure component. Renders título, autores (joined), fecha (año), área (display name via the áreas tree), tipo (display label), abstract (truncated ~280 chars), snippet (~200 chars). Highlights matched terms in the snippet when the row came from a lexical hit (server already injected `<mark>` via `ts_headline`).

**Responsibilities:** Card layout and responsive scaling for mobile (PRD §24). Truncation discipline.

**Seams:** None.

**Depth note:** Shallow but earns isolation as the single visual contract for a search result; reused unchanged when PRD-4 lands related-document cards.

---

### `app/buscar/EmptyState.tsx`

**Interface:** Props: `{ activeFilters: FilterChip[], onClearOne, onClearAll }`. Renders chips per active filter with one-click clear (PRD §16, §21).

**Responsibilities:** Recovery UX surface — empty-result and clear flow. Owns the chip-from-filter projection (e.g., `area=ingenieria_informatica` → "Ingeniería Informática").

**Seams:** None.

**Depth note:** Borderline split from page. Earns its own file because the chip-projection logic is non-trivial (slug → display name via áreas tree) and the surface needs Playwright coverage independent of the result list.

---

## Dependency graph

```
                       app/buscar/page.tsx
                      /        |         \
              useSearch   SearchFilters   EmptyState
                |              |               |
              fetch        AreasCascader   (display)
                |              |
                |          GET /api/areas
                |              |
                |          api/areas
                |              |
                |          (Postgres: áreas table)
                |
              GET /api/search
                |
              api/search (validation + DTO)
                |
              core/search (execute) ─── core/embed ─── TEI sidecar
                |
              core/search_query ─── core/document_access (invitado_where)
                |
              (Postgres: chunks + documents + áreas)
```

No cycles. The frontend talks to FastAPI only through the typed OpenAPI client (ADR-0004 §6); no Server Components in this slice.

## Out of scope

- **`/docs/[id]` detail page and `ResultCard` click target** — PRD #4 owns navigation destination.
- **`interno` / `privado` visibility branches and login UI** — PRD #2; `document_access` will grow `readable_fragment(user_ctx)` then.
- **Indexing pipeline (extraction, embedding-passage, headline lifecycle)** — PRD #3.
- **`core/snippet.py`** — rejected. `ts_headline` and abstract-prefix are SQL inside `search_query`; no second caller justifies extraction.
- **`SearchResults` list component** — rejected. The page-20 nudge + result count line are one conditional; a wrapper would be a pass-through (deletion test fails).
- **Lexical-fallback UI banner** — rejected by PRD ("silent. No banner."); `isLexicalFallback` from `useSearch` is for telemetry only.
- **`MIN_SEMANTIC_SIMILARITY` calibration tooling** — committed fixture + offline notebook per ADR-0001 §12; not a runtime module.
- **`core/areas.py` domain module** — premature; the áreas tree has no behaviour beyond "fetch all," which lives in the router.
