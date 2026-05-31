# Module Map: Discovery — Más leídos & catalog size

## Source

No PRD issue. Designed from a session plan locked with the maintainer (search-landing
redesign + read tracking). Sliced by `/to-issues` into 5 implementation tickets.

Implements the redesigned `/buscar` landing (chatbot-style "Prompt" mockup at
`docs/design/mockup/js/screens-auth.jsx`) backed by two new datums: a **más
leídos** ranking and the público catalog size. Extends the reader chokepoint from
[document-detail.md](document-detail.md) (`api/docs`, `get_doc_detail`) and the
landing from [search-mvp.md](search-mvp.md) (`/buscar`). Reuses the access policy
in ADR-0010 §6-§8 — introduces no new access predicate.

See `CONTEXT.md` for **lectura** and **más leídos**.

## Modules

### `document_reads` (migration 0020)

**Interface:** A row is one (`doc_id`, `reader_key`, `read_day`) tuple — the primary
key. `reader_key` is the **lectura** dedup identity: `u:{user_id}` for an
authenticated reader, `a:{anon_id}` for an **Invitado**. `doc_id` FKs `documents`
`ON DELETE CASCADE` (a hard-deleted/purged document drops its reads). The PK *is*
the once-per-reader-per-doc-per-day invariant; writers rely on
`INSERT … ON CONFLICT DO NOTHING`. Index on `(read_day, doc_id)` serves the
rolling-window aggregation.

**Responsibilities:** Persist deduped **lecturas**. No application logic.

**Depth note:** The dedup invariant lives in the schema (PK), not in N call sites.
Deletion test: without the unique key, every caller would re-implement
"have I already counted this reader today?" — it concentrates here.

---

### `core/discovery`

**Interface:**
- `record_read(session, doc_id, reader_key)` — idempotent insert of one **lectura**;
  no-op on conflict; never raises on a duplicate. Sole writer of `document_reads`.
  Records for any opened document regardless of visibility (the público filter is a
  read-time concern of `most_read`, not a write-time one).
- `most_read(session, *, window_days, limit)` — the **más leídos** ranking:
  público documents (via `core/document_access.invitado_where`) ordered by distinct
  **lectura** count within the rolling `window_days`, capped at `limit`. Returns rows
  carrying `doc_id, titulo, area_path, tipo, fecha, reads`. One shared ranking — takes
  no `UserCtx`.

**Responsibilities:** Own all reads/writes of `document_reads`. Translate raw
**lecturas** into the público ranking.

**Depth note:** Sole owner of the reads table; the dedup-insert and the
window-aggregate query concentrate here behind two small functions. Deletion test:
scatters two non-trivial SQL shapes across `api/docs` otherwise.

**Out of cohesion (deliberate):** `count_public_documents` does NOT live here — it
never touches `document_reads`. It belongs to `core/search` (below).

---

### `core/search` (extended)

**Interface (added):** `count_public_documents(session) -> int` — the público catalog
size for the landing footnote. Counts `documents` under
`core/document_access.invitado_where`. No query, no filters — the unfiltered público
total.

**Depth note:** `core/search` already owns counting (`run_count`) and the
público-corpus read surface (search-mvp.md). The catalog count is one more count over
the same predicate, not a new module.

---

### `core/auth` (extended)

**Interface (added):** `reader_key(user_ctx, request, response) -> str` — resolves the
**lectura** dedup identity. Authenticated → `u:{user_id}` (no cookie). **Invitado** →
reads the `rid` cookie, minting an opaque random one (httponly, `samesite=lax`, long
max-age) onto `response` when absent, → `a:{anon_id}`.

**Responsibilities:** Concentrate the `rid` cookie minting with the existing session
cookie machinery.

**Depth note:** `core/auth`'s charter is to concentrate the audit/cookie surface in one
module (its docstring). The anon-tracking cookie is a cookie concern; it belongs with
`_set_sid_cookie`, not spread into `api/docs`. Deletion test: callers (`api/docs`) stay
one line — `key = auth.reader_key(ctx, req, resp)`.

---

### `api/docs` (extended)

**Interface (added):**
- Read recording: `get_doc_detail` calls `record_read` after resolving a real detail
  (a `DetailDTO` / `DetailWithInvitationDTO` — **never** for `MinimalInviteDTO`, a
  download, or a 404). Uses `auth.reader_key`. Recording shares the request transaction
  (`get_session` commit-at-exit); a failed handler rolls the **lectura** back with it.
- `GET /api/docs/popular?window=week&limit=3` → `{ results: [...], public_total: int }`.
  `results` is the **más leídos** list (`most_read`); `public_total` is
  `count_public_documents`. One round-trip feeds both landing datums. `window` accepts
  `week` (→ 7 days); `limit` defaults small and is capped.

**Responsibilities:** Transport only — query parsing, DTO projection, calling
`core/discovery` + `core/search`. No ranking or access logic.

**Depth note:** Reuses the existing reader router/chokepoint; adds one endpoint and one
recording call. The `public_total` co-location (vs a separate `/api/stats`) keeps the
landing to a single fetch.

---

### Frontend — `useMostRead`

**Interface:** React-query hook over the openapi-fetch client (`api/client.ts`), mirroring
`useSearch`/`useUser`. Calls `GET /api/docs/popular`, returns `{ results, publicTotal,
isLoading, isError }`. Single source for both the **más leídos** list and the catalog
count footnote.

**Depth note:** Shallow data adapter; earns its place as the typed seam between the
generated schema and `SearchLanding`.

---

### Frontend — `SearchLanding`

**Interface:** `buscar/SearchLanding.tsx`, rendered by `buscar/page.tsx` on the
`!showResults` branch in place of the old hero. Composes: time-of-day greeting + first
name (`useUser`; **Invitado** → greeting with no name), chatbot composer (textarea + ↩
hint + send → navigates `/buscar?q=`), static suggested-query chips, the **más leídos**
top-N list (`useMostRead`; `area_path`→escuela via `useAreaLabel`, `tipo` via
`TIPO_LABEL`), and the "Buscando en N trabajos" footnote (`publicTotal`).

**Responsibilities:** The landing view composition. Independently testable, isolated from
the results branch.

**Depth note:** Extraction concentrates the redesign in one file; `page.tsx` keeps only
the `showResults` branch decision.

## Dependency graph

```
document_reads (migration 0020)
        ▲
core/discovery ──uses──> core/document_access.invitado_where
core/search   ──uses──> core/document_access.invitado_where   (count_public_documents)
core/auth.reader_key
        ▲           ▲
        └───────────┴── api/docs (get_doc_detail recording + GET /api/docs/popular)
                                ▲
                          useMostRead ──> SearchLanding <── useUser, useAreaLabel, TIPO_LABEL
                                                ▲
                                          buscar/page.tsx (!showResults)
```

No cycles. `core/discovery` and `core/search` both depend on `core/document_access`
(shared predicate, intended). Frontend is strictly downstream of `api/docs` (the FE types
are generated from the running backend).

## Out of scope

- **Periodic retention/purge of `document_reads`** — raw **lecturas** are kept; a purge
  job is future work. Recorded so it isn't assumed shipped.
- **Popularity influencing search ranking** — SPEC §Ranking keeps RRF with no popularity
  or recency boost; **más leídos** is a display surface only. Do not wire reads into
  `core/search_query` fusion.
- **Per-viewer / personalized más leídos** — the ranking is público-only and shared; no
  `UserCtx` in `most_read`.
- **Counting downloads as lecturas** — only `get_doc_detail` records; download endpoints
  do not.
- **A dedicated `/api/stats` router** — considered and rejected; the catalog count rides
  on `GET /api/docs/popular` as `public_total` to keep the landing to one fetch.
- **A new access predicate** — `most_read` and `count_public_documents` reuse
  `invitado_where`; no new fragment in `core/document_access`.
