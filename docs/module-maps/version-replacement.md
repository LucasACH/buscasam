# Module Map: Document versioning — file replacement and candidate versions

## Source

PRD: [Issue #56 — Document versioning: file replacement and candidate versions](https://github.com/LucasACH/buscasam/issues/56).

Implements the candidate-version slice on a published document: author uploads a replacement file as a candidate that processes alongside the previously published version, reviews its status on `/mis-trabajos/{id}/editar`, and either publishes (atomic swap, ADR-0006 §6) or descartar. Lands the at-most-one-candidate invariant, the `'discarded'` terminal state, and the `first_published_at` gate from ADR-0011. Extends `core/documents` and `api/documents` along the chokepoints already established in [document-publication.md](document-publication.md); reuses `manageable_where` from ADR-0010 §8. Narrows the historic-version surface already shipped by [document-detail.md](document-detail.md).

## Modules

### `core/documents` — touched, adds `replace_main_version` + `discard_candidate`

**New surface:**

```python
async def replace_main_version(
    session: AsyncSession,
    user_ctx: UserCtx,
    doc_id: DocId,
    blob: BlobPutResult,
    *,
    original_filename: str,
) -> VersionId
# - Manageable-scoped (owner | accepted coauthor); cross-user → 404.
# - Asserts a published current version exists; otherwise NoPublishedVersion → 409.
# - If a non-discarded candidate exists, transitions it to 'discarded' inline
#   (same SQL semantics as discard_candidate) so the partial unique index admits
#   the new row.
# - Inserts document_versions: version_no = MAX(version_no)+1, index_status='pending',
#   is_current=false, first_published_at=NULL.
# - Pre-fills staged_abstract/staged_keywords/staged_fecha from documents.* so
#   polling clients see sensible values before extraction completes. Worker
#   overwrites with derive_metadata() output on completion (uniform contract).
# - Enqueues index_document(version_id) through the same transaction.

async def discard_candidate(
    session: AsyncSession,
    user_ctx: UserCtx,
    doc_id: DocId,
) -> None
# - Manageable-scoped. Selects the candidate row (is_current=false AND
#   index_status <> 'discarded') FOR UPDATE; raises NoCandidateToDiscard → 404 if none.
# - Sets index_status='discarded'. Deletes that version's chunks (always
#   is_current=false, so search visibility is unchanged). Does not delete
#   the document_versions row; does not delete the blob (orphan sweep handles it).
```

**Extended surfaces:**

- `_begin_indexing(version_id)` (private worker entry) — its row-locked short-circuit grows a `'discarded'` branch returning `None` (ADR-0011 §5). Worker writes (`write_indexed_candidate`, `mark_failed`, `write_headline`) continue to be gated by `WHERE index_status='processing'` / `WHERE index_status='indexed' AND id=:version_id`, so a descartar transition committed between the lock release and the worker write aborts the write atomically. No new worker function.
- `publish` — the atomic publish SQL block additionally sets `first_published_at = now()` on the candidate row when its current value is `NULL`. Immutable once set; a republish does not re-stamp it. The `chunks.is_current` flip, `documents.publication_status`, and `documents.{abstract,keywords,fecha} <- staged_*` rules are unchanged.
- `update_draft_metadata` — write-through behavior unchanged on `documents.*` (post-publish edits persist immediately + enqueue headline reindex for the published version, ADR-0010 §4). Additionally, when a non-discarded candidate exists, writes title/abstract/keywords/fecha to its `staged_*` and invalidates the candidate's `headline_fingerprint`, enqueuing `refresh_headline(candidate_version_id)`. The two reindexes are independent per ADR-0008 §3 (`headline:v{id}` locks).
- `get_draft_state` — payload extended with `candidate: CandidateState | null` (status, staged_abstract, staged_keywords, staged_fecha, can_discard, can_publish, indexed_at, error) and `versions: DetailVersion[]` filtered on `first_published_at IS NOT NULL`. Polling remains 3000 ms while either the published headline reindex or the candidate is in flight (raw status driven by `candidate.status`).
- `get_detail` projection — `versions: list[DetailVersion]` now filters on `first_published_at IS NOT NULL`. Failed candidates, discarded candidates, and in-flight ready candidates do not appear in the manager-visible Versiones list on `/docs/{id}`.
- `get_manageable_version_file(doc_id, n, user_ctx)` (existing download lookup behind `GET /api/docs/{id}/versions/{n}/download`) — adds `AND first_published_at IS NOT NULL` to the WHERE clause. Failed/discarded/in-flight ready versions return `None` (uniform 404), regardless of role.

Invariants: every author-facing function takes `user_ctx` and applies `manageable_where`; cross-user → 404 (ADR-0010 §7). The chokepoint remains the **only writer** of `document_versions` — an architecture test extends the existing rule (ADR-0011 §12). The partial unique index `document_versions_one_candidate` (see schema, below) enforces at-most-one at the database boundary; `replace_main_version` discards any pre-existing candidate in the same transaction so the index admits the new insert.

**Responsibilities:** Sole writer of `document_versions`. Owns the at-most-one-candidate inline discard, the `first_published_at` stamping on publish, the candidate-vs-published `staged_*` fan-out during edits, the worker discarded-gate, the `get_draft_state` candidate projection, and the `first_published_at` narrowing of `get_detail.versions` / `get_manageable_version_file`. Owns the `NoPublishedVersion` (409) and `NoCandidateToDiscard` (404) domain exceptions.

**Seams:** None added. ADR-0011 explicitly rejects a `core/candidate` split: the at-most-one invariant, the `discard_candidate` inline call inside `replace_main_version`, and the publish transaction all share enough state that splitting would force them to re-cross modules per call. Single domain chokepoint per `document-publication.md` is preserved.

**Depth note:** Three new invariants stack here — at-most-one-candidate (database + chokepoint guard), worker discarded-gate (no resurrected writes), `first_published_at` immutability (audit gate). Deletion test: scattering `replace_main_version`'s "discard any pre-existing candidate inline" into the router would race with concurrent uploads (the partial unique index would still hold, but the API contract would surface as a 500 on the second caller instead of a clean replacement); a separate `core/candidate` would force `publish` to coordinate `first_published_at` across a module boundary. The same single-module argument that publication.md locks for `publish` extends to replacement.

---

### `api/documents` — touched, adds two endpoints

**New surface:**

```
POST   /api/documents/{id}/replace       202 / 404 / 409 / 413 / 415   (require_authenticated, manageable)
DELETE /api/documents/{id}/candidate     204 / 404                     (require_authenticated, manageable)
```

`POST /replace` is `multipart/form-data` direct to FastAPI (mirrors `POST /upload`, ADR-0004 §8). The route streams into `blob_store.put_stream(max_bytes=50_000_000)` (413 surfaced inline with "Este archivo supera los 50 MB"), validates `sniffed_mime` against `{pdf, docx, odt}` (415), calls `extract.probe_encrypted(head_bytes)` for PDFs before `put_stream` so an encrypted PDF never hits disk (415), then `documents.replace_main_version(...)` and returns `202`. `NoPublishedVersion` from `replace_main_version` maps to 409 ("El documento aún no tiene una versión publicada"). Cross-user manageable check returns 404 to avoid existence leakage.

`DELETE /candidate` is singular by contract — at most one candidate exists per document, so the endpoint identifies it by `doc_id` alone (ADR-0011 §9). `NoCandidateToDiscard` from `discard_candidate` maps to 404.

`POST /upload` retains its initial-publication-only semantics: inserting on a document that already has a published current version raises `AlreadyPublished` → 409. `POST /replace` is the inverse (callable only when a published current version exists). Each endpoint has a single legal entry state; the router cannot cross them.

Publish remains owner-only (`POST /api/documents/{id}/publish`, existing surface from document-publication.md), so `replace_main_version` + `discard_candidate` are accessible to accepted coauthors but only the owner can finalize the swap. The owner gate stays where it already lives (in the publish route's dependency), not in `replace_main_version`.

**Responsibilities:** HTTP edge for the two new routes. Streams `multipart` uploads through `blob_store`, performs the sync MIME + encrypted-PDF gate, maps domain exceptions to status codes, and emits the no-leak 404 envelope on manageable misses. Never opens transactions; never writes `document_versions` directly.

**Seams:** None. ADR-0011 §9 + PRD §"Out of Scope" reject an `api/versions` router split — both endpoints are document-scoped, share the same auth dep set, and reuse the same `core/documents` chokepoint as the existing upload/publish routes.

**Depth note:** Thin by design. The depth lives in `core/documents`. The router's job is the synchronous-rejection surface (413/415), the singular `/candidate` URL shape, and the no-leak 404 envelope.

---

### `api/docs` — touched, narrowed predicate on historic-version download

**Surface unchanged:**

```
GET /api/docs/{id}/versions/{n}/download   → X-Accel-Redirect (200) | 404
```

The route already lives in [document-detail.md](document-detail.md) and was the first endpoint to consume a non-current `document_versions` row. PRD #56's only change is the `first_published_at IS NOT NULL` filter inside `core/documents.get_manageable_version_file` (the SQL lookup the route uses). Versions that were never public — failed candidates, discarded candidates, in-flight ready candidates — uniformly resolve to `None` → 404, regardless of role. No router-level change; the no-leak 404 envelope is unchanged.

**Responsibilities:** Unchanged from document-detail.md. PRD #56 only narrows the predicate the existing lookup enforces.

**Seams:** None.

**Depth note:** This is exactly the reason `get_manageable_version_file` is a chokepoint and not inline router SQL — the predicate narrowed in one place automatically rolled through to the route.

---

### `core/jobs` — interface unchanged

The `index_document`, `ocr_index_document`, and `refresh_headline` task bodies have no new code surface. `_begin_indexing`'s new `'discarded'` short-circuit is owned by `core/documents` (called from the task body just as today). `refresh_headline`'s existing `WHERE index_status='indexed' AND id=:version_id` write guard naturally no-ops on a discarded candidate; the worker-cancel-by-SQL pattern (ADR-0008 §3) already covers this case without modification.

A descartar issued mid-extraction commits its `index_status='discarded'` transition; when the worker next attempts `write_indexed_candidate`, the gated WHERE clause matches zero rows and the worker exits silently. No hard-kill mechanism is needed (PRD §"Out of Scope" explicitly rejects one).

**Responsibilities:** Unchanged. The async edge contracts from document-publication.md still hold.

**Seams:** None.

**Depth note:** The fact that this PRD ships without touching `core/jobs` is the validation of the publication.md chokepoint design — the discarded transition is a row-state change, not a new task body or a new queue.

---

### `app/mis-trabajos/[id]/editar/page.tsx` — touched

**Surface added:**

- Mounts `<CandidatePanel docId canPublish={isOwner} />` on a published document. The panel auto-resolves its visual state from `useDraftState`'s `candidate` field.
- Mounts `<VersionsPanel docId versions={state.versions} canManage />` (always manageable on this route). The data the panel receives is already filtered on `first_published_at IS NOT NULL` server-side.
- The metadata form and Publicar/Suggestions wiring are unchanged. While a candidate is in flight, edits to título/abstract/keywords/fecha apply to the published `documents` row immediately (existing post-publish edit semantics) AND fan out to the candidate's `staged_*` server-side — the page does not need to know about the dual-write.

**Responsibilities:** Adds the `<CandidatePanel>` + `<VersionsPanel>` placements and forwards `isOwner` for the owner-only Publicar affordance. Page-level layout only; lifecycle interpretation stays in `useDraftState`.

**Seams:** None.

**Depth note:** The page remains layout + form-wiring. The candidate UX concentrates in `CandidatePanel`, and the data fan-out concentrates in `useDraftState` — the page's job is to mount them and pass the owner flag.

---

### `app/mis-trabajos/useDraftState.ts` — touched

**Surface added:**

```ts
useDraftState(docId: number) -> {
  state: {
    // existing fields: title, staged_abstract, staged_keywords, staged_fecha, lifecycle, ...
    candidate: {
      status: 'processing' | 'ready' | 'failed';
      statusLabel: string;             // Procesando… / Listo para publicar / Falló el procesamiento
      helperLabel: string;             // helper line under Reemplazar; localized
      stagedAbstract: string;
      stagedKeywords: string[];
      stagedFecha: string | null;
      canPublish: boolean;             // owner-only
      canDiscard: boolean;             // manageable
      error: string | null;            // populated on status='failed'
    } | null;
    versions: DetailVersion[];          // server-filtered on first_published_at IS NOT NULL
  } | undefined;
  // existing: isLoading, isError, refresh
  replace(file: File): Promise<ReplaceMutationError | undefined>;
  discard(): Promise<DiscardMutationError | undefined>;
}
```

`replace(file)` posts `multipart/form-data` to `POST /api/documents/{id}/replace` (direct browser request — the generated OpenAPI body type cannot represent runtime `File`, same constraint as `useDraftAttachments`). Surfaces 413/415/409 as `ReplaceMutationError` for the panel's inline copy. Optimistically invalidates the draft query so the panel transitions to `processing` immediately; the next poll picks up the real `version_id`.

`discard()` posts `DELETE /api/documents/{id}/candidate`. Optimistically removes `candidate` from the cached state; on rollback (404 race) refetches.

Polling cadence remains 3000 ms while EITHER `lifecycle.publishGateReason` denotes processing/reindexing the published headline OR `candidate?.status === 'processing'`. Idle when both surfaces are quiet (or when `candidate.status === 'failed'`, awaiting user action — the failed status itself is steady).

`candidate.statusLabel` / `helperLabel` are Spanish; the server returns `candidate.status` only. The Spanish/UI projection lives here, consistent with the existing `lifecycle.statusLabel` rule.

**Responsibilities:** Request shape for the two new mutations, optimistic cache updates, candidate-aware polling cadence, raw-status-to-Spanish-label projection for the candidate surface. The backend remains the source of truth for `can_publish` / `can_discard` (the hook does not derive them from `isOwner` client-side).

**Seams:** None.

**Depth note:** Same depth argument as document-publication.md — cadence, lifecycle interpretation, and mutation invalidation are one staged-publication rule bundle. Adding `candidate` as a sibling of `lifecycle` rather than collapsing them keeps the post-publish edit semantics (form behavior) and the candidate lifecycle (panel behavior) independently expressible, which is what PRD story 14 + story 37 require.

---

### `components/CandidatePanel.tsx` — new

**Interface:**

```ts
type Props = {
  docId: number;
  canPublish: boolean;       // owner-only; from page
};
```

Consumes `useDraftState(docId)`. Renders one of four states based on `state.candidate`:

- **No candidate** (`candidate === null`) — renders the **Reemplazar archivo principal** button (file picker with `accept=".pdf,.docx,.odt"`) and a helper line below it: *"La versión previa permanece pública hasta que publiques la nueva."* (PRD stories 11/13). Click on the file picker triggers `replace(file)`; inline error rendering for 413 ("Este archivo supera los 50 MB"), 415 ("Formato no soportado o PDF cifrado"), 409 (defensive; should not happen from this state).
- **Processing** (`candidate.status === 'processing'`) — renders status pill *"Procesando…"*, the file's `original_filename`, and a **Descartar** button (visible when `canDiscard`). No suggestion display (staged_* still defaults from `documents.*`; nothing to compare yet). Optionally renders the Reemplazar button to replace the in-flight candidate (PRD story 8) — clicking it replaces the existing candidate per the chokepoint's inline-discard semantics.
- **Ready** (`candidate.status === 'ready'`) — renders status pill *"Listo para publicar"*, the staged abstract/keywords/fecha alongside the published values from `state` (so the author can compare), a **Publicar** button (enabled iff `canPublish`), and a **Descartar** button. **Publicar** posts to the existing `POST /api/documents/{id}/publish` route. The existing publish-gate copy (gate reason → Spanish) for the published headline reindex still gates the button (the published doc cannot publish a candidate mid-reindex of its own headline, same fingerprint rule).
- **Failed** (`candidate.status === 'failed'`) — renders status pill *"Falló el procesamiento"* with `candidate.error` rendered inline, and a **Descartar** button. After descartar, the panel returns to the no-candidate state, where Reemplazar is re-enabled.

`canPublish` is forwarded from the page (owner-only); `canDiscard` comes from the server through `state.candidate`.

**Responsibilities:** Single concentration of the candidate UX — the Reemplazar affordance, the four status renderings, the helper line, the suggestions-vs-published comparison block, the Publicar button (when `canPublish`), and the Descartar button. Owns all Spanish copy for replacement (status pills, helper, inline error messages).

**Seams:** None.

**Depth note:** Deletion test: scatter the Reemplazar button + helper line + status pill + comparison block + Descartar across the editar page and the suggestions panel, and the "candidate exists" mental model fragments — the helper line ("la versión previa permanece pública") would drift from the Reemplazar trigger, the comparison block would reach into staged_* without knowing the candidate's status, and the Descartar wiring would duplicate in two places. Concentration here makes the four-state UX one audit surface. Single caller at MVP (the editar page); per the panel-location decision in PRD §"Out of Scope", the candidate panel is explicitly NOT mounted on `/docs/{id}` for managers — they use `/mis-trabajos/{id}/editar`. Earns isolation regardless because the panel is the auditable place where the "previous version stays public" contract is communicated to the author.

---

### `components/VersionsPanel.tsx` — touched (interface unchanged)

Already shipped by document-detail.md. PRD #56 narrows what the panel receives (server-side `first_published_at IS NOT NULL` filter), but the prop contract — `{ docId, versions, canManage }` — is unchanged. The panel's rendering of the current row with `(actual)` annotation (story 26) already exists. Failed/discarded/in-flight ready candidates simply do not appear in the `versions` array.

**Responsibilities:** Unchanged.

**Seams:** None.

**Depth note:** Same as document-detail.md. PRD #56 validates the prop-as-filter design — the predicate change happened server-side and rolled through automatically.

---

## Touched, not new

- **`core/document_access`** — no new adapter. `manageable_where` gains additional callers in `replace_main_version` and `discard_candidate`, joining the existing roster from document-publication.md.
- **`core/blob_store`** — no interface change. `put_stream(max_bytes=50_000_000)` is the same call the initial-upload route makes; dedup via sha256 means a replacement that happens to match the previous file's bytes shares a blob (orphan sweep handles cleanup once no row references the sha256).
- **`core/extract`** — no change. `probe_encrypted` is reused at the `POST /replace` edge; the worker's `extract` + `derive_metadata` pipeline is uniform across initial and replacement extraction (ADR-0011 §7).
- **`schema (migration 0011)`** — adds `document_versions.first_published_at timestamptz` (nullable); adds the partial unique index `document_versions_one_candidate ON document_versions (doc_id) WHERE is_current = false AND index_status <> 'discarded'`; adds `'discarded'` to the `index_status` value set (text CHECK if introduced). Backfill: existing `is_current = true` rows get `first_published_at = uploaded_at` (best-effort proxy on a small corpus, ADR-0011 §3). Round-trip migration test pattern from `test_migration_0010_round_trip.py`. Schema-existence assertion in `test_indices.py`.
- **OpenAPI / typed client** — regenerated to expose the two new endpoints and the extended `DraftState` DTO (`candidate`, `versions` fields). The frontend's typed mutations consume them; the multipart `File` body on `POST /replace` is the existing browser-direct exception.

## Dependency graph

```
                           app/mis-trabajos/[id]/editar/page.tsx
                              /         |              |          \
                useDraftState   CandidatePanel     VersionsPanel    metadata form
                    |                  |                |                |
                    |                  └─ replace(file) / discard() ─┐   |
                    |                                                 |   |
              GET /api/documents/{id}/draft       (returns candidate + versions)
              POST /api/documents/{id}/replace   ───────────────────┐ |   |
              DELETE /api/documents/{id}/candidate ────────────────┐│ |   |
              POST /api/documents/{id}/publish    (existing)      ││ |   |
              PATCH /api/documents/{id}           (existing) ─────┼┼─┼───┘
                                                                  ││ |
                                                       api/documents
                                                                  |
                                                       core/documents
                                                  ┌───────────────┼───────────────┐
                                          replace_main_version  discard_candidate  get_draft_state
                                          (manageable)          (manageable)        (manageable, extended)
                                                  |                |                  |
                                                  |                |          publish (sets first_published_at)
                                                  |                |          update_draft_metadata (fan-out to candidate)
                                                  └────────────────┴─── core/document_access.manageable_where
                                                                          |
                                                       (Postgres: document_versions
                                                        — partial unique index enforces
                                                        at-most-one candidate)
                                                                          |
                                                                          |◄── enqueue (transactional)
                                                                          |
                                                                      core/jobs
                                                                          |
                                                       index_document task body
                                                       (calls _begin_indexing, gated by
                                                        index_status in WHERE; discarded
                                                        gate aborts writes atomically)

  (historic-version download — touched predicate)
                  GET /api/docs/{id}/versions/{n}/download
                            |
                  api/docs ──► core/documents.get_manageable_version_file
                                  (WHERE first_published_at IS NOT NULL
                                   AND manageable_where)
                            |
                            └──► core/blob_store.internal_path ──► X-Accel-Redirect
```

No cycles. The new endpoints reuse the existing `core/documents` → `core/document_access` → `core/jobs` (enqueue) graph from document-publication.md without introducing new edges. The historic-version download edge from document-detail.md is unchanged in shape; only the SQL predicate inside `core/documents.get_manageable_version_file` narrows.

## Out of scope

- **`core/candidate` split** — rejected (ADR-0011 §12 + PRD §"Out of Scope"). The at-most-one invariant, the inline-discard inside `replace_main_version`, and the publish transaction share enough state that splitting would force them to re-cross modules per call.
- **`api/versions` separate router** — rejected. Two new endpoints, both document-scoped, both manageable, both reuse the `core/documents` chokepoint. The historic-version download already lives in `api/docs` (reader-facing) by design.
- **`current_version_id` denormalized back-pointer on `documents`** — rejected (ADR-0006 §5). Reads keep joining on `is_current = true`.
- **CandidatePanel on `/docs/{id}` for managers** — rejected per PRD §"Out of Scope". Managers use `/mis-trabajos/{id}/editar` for candidate state; the detail page's manager affordances remain Editar + Versiones panel.
- **Promoting a historic version back to current ("rollback" UI)** — rejected at MVP. The Versiones panel is read-only audit.
- **Candidate diff UI** (showing extracted-text differences between current and candidate) — rejected at MVP.
- **Per-version metadata edits** — rejected. Every `staged_*` edit applies to the candidate; historic versions' metadata is frozen.
- **Worker hard-kill mechanism for descartar** — rejected. The SQL `WHERE index_status='processing'` gate on the worker writes is the abort contract; no external signal is sent to OCR or default workers (ADR-0011 §5, §10).
- **Email notification on candidate ready / processing_failed** — rejected. In-app only (ADR-0010 §9, SPEC §Estados).
- **Reader-facing surfaces (search, detail page, Trabajos relacionados, sitemap, public downloads, attachments)** — out of this PRD's window. They continue to gate on `is_current = true` rows only (ADR-0011 §11). A reader path consulting `first_published_at` would be a bug.
- **Combined replace+publish UI ("subir y publicar de una")** — rejected. Publish is always an explicit second click; the panel surfaces Publicar separately so no replacement ever goes public without confirmation (PRD story 4).
- **Optimistic publish on the panel** — rejected. The publish gate already lives in `useDraftState` for the existing flow; the panel's Publicar reuses the same 409-refresh path.
- **A separate `useCandidate(docId)` hook** — rejected. The candidate's status, the published headline reindex, and the metadata form all share the same `GET /draft` polling endpoint; splitting the hook would force two query keys to coordinate the same payload.

## Further Notes

- `documents.publication_status` never changes during replacement. The document stays `published`; the entire candidate state machine lives in `document_versions.index_status` + `is_current` + `first_published_at`.
- `POST /upload` and `POST /replace` are deliberately split, each with a single legal entry state. `/upload` refuses (409) on a doc with a published current version; `/replace` refuses (409) on a doc without one. The chokepoint cannot accidentally cross-purpose them.
- `staged_*` pre-fill from `documents.*` is a UX nicety for the polling window only. The worker is uniform across initial and replacement extraction and always overwrites `staged_*` with `derive_metadata()` output (ADR-0007 §2, ADR-0011 §7). The author's curated metadata is preserved through `update_draft_metadata`'s write-through to `documents.*`, not through the `staged_*` initial value.
- The `processing_failed` notification's `event_key` for a candidate is `processing_failed:{version_id}` (existing unique index, ADR-0010 §9). A retry that re-fails the same version cannot create a duplicate notification.
- `first_published_at` is the audit gate, not a security gate. The reader-facing path stays on `is_current = true` (search, related, detail metadata, current download, attachments, sitemap). `first_published_at` is consulted by exactly two paths: `get_manageable_version_file` (the historic download), and `get_detail.versions` / `get_draft_state.versions` (the Versiones list projection).
- The partial unique index `document_versions_one_candidate` is the database-boundary enforcement; the API contract + the inline-discard in `replace_main_version` is the cooperating chokepoint guard. The architecture test from publication.md extends to forbid `document_versions` writes outside `core/documents`.
- Migration 0011 round-trip test runs on top of `test_migration_0010_round_trip.py`'s fixture state, validating that adding the column + partial unique index + `'discarded'` value, then reverting, leaves the database byte-equivalent.
