# Module Map: Document publication flow (draft → upload → extract → review → publish)

## Source

PRD: [Issue #25 — Document publication flow: draft, upload, extract, review, publish](https://github.com/LucasACH/buscasam/issues/25).

Implements the `/mis-trabajos` slice end-to-end: single-step draft form, async extraction/indexing pipeline (PDF/DOCX/ODT + OCR gate), staged-metadata review, publish transaction with headline-fingerprint check, attachment management before and after publish. Lands the ADR-0006 (`blob_store`), ADR-0007 (`extract`), and ADR-0008 (`jobs`) chokepoints introduced in this PRD; extends `document_access` with the manageable-by-author predicate.

## Modules

### `core/blob_store`

**Interface:** Per ADR-0006 §3, sole surface:

```python
@dataclass(frozen=True)
class BlobPutResult:
    sha256: str            # 64 hex chars
    bytes: int
    sniffed_mime: str      # libmagic over first 2 KB

async def put_stream(stream: AsyncIterator[bytes], *, max_bytes: int) -> BlobPutResult
async def open_for_send(sha256: str) -> AsyncIterator[bytes]
def internal_path(sha256: str) -> str          # for X-Accel-Redirect
async def exists(sha256: str) -> bool
async def delete(sha256: str) -> None          # GC only
```

Invariants: content-addressed sha256 with two-level shard (ADR-0006 §2); atomic write through `/blobs/.tmp/<uuid4>.partial` → `fsync` → `os.rename` (§4); rename collision = dedup hit, temp file unlinked; `put_stream` raises if streamed bytes exceed `max_bytes` (caller-supplied per file class — 50 MB main, 20 MB attachment); startup hook sweeps `.tmp/` older than 24 h. Architecture tests forbid application reads/writes/deletes outside this module (§3).

**Responsibilities:** Every byte hitting `/var/lib/buscasam/blobs/` goes through here. Owns the temp+rename protocol, the sharded path computation, MIME sniff via `libmagic`, the `X-Accel-Redirect` internal-path projection, and the orphan-sweep entry that `core/jobs` periodic task calls.

**Seams:** None at MVP. The local filesystem backend is the only implementation; ADR-0006 §1 locks it. An object-store adapter is post-MVP.

**Depth note:** The single auditable place bytes hit disk (PRD story 35). Deletion test: atomic-write semantics, sharding, dedup, and `X-Accel-Redirect` path computation would scatter across upload routes, GC workers, and download routes — each subtly drift-prone. ADR-0006 §3 locks the chokepoint.

---

### `core/extract`

**Interface:** Per ADR-0007 §2, two pure surfaces plus a synchronous probe:

```python
@dataclass(frozen=True)
class ExtractedDoc:
    text: str
    paragraph_breaks: list[int]    # ascending byte offsets
    page_breaks: list[int]         # empty for DOCX/ODT
    raw_metadata: dict

@dataclass(frozen=True)
class IndexableMetadata:
    abstract: str                  # may be ""
    keywords: list[str]            # 0..10
    fecha: date | None             # caller falls back to upload date

async def extract(sha256: str, mime: str) -> ExtractedDoc
def derive_metadata(doc: ExtractedDoc) -> IndexableMetadata
def probe_encrypted(head_bytes: bytes) -> None  # raises PDFEncryptionError → 415
```

Invariants: per-format dispatch is internal; callers pass `mime` (already sniffed by `blob_store`). The OCR gate (ADR-0007 §4) is an inline branch — if `pdfminer.six` yields < 100 chars/page averaged on a PDF, `extract` raises `OCRRequired(sha256)` so `core/jobs` can re-enqueue on the `ocr` queue; otherwise `extract` returns inline. `derive_metadata` is pure and synchronous. Empty body is not a failure (`abstract=""`, `keywords=[]`, `fecha=None`); ADR-0007 §9.

**Responsibilities:** Single chokepoint for "PDF/DOCX/ODT → text + offsets" and "text → abstract/keywords/fecha suggestions" (ADR-0007 §1). Owns the `pdfminer.six` / `python-docx` / `odfpy` dispatch, the `ocrmypdf` invocation on the `ocr` worker, the OCR threshold, the `Resumen|Abstract|...` regex, the YAKE configuration, the fecha cover-page heuristic, and the encrypted-PDF probe.

**Seams:** **Real seam.** Three format adapters today (PDF / DOCX / ODT), all materialized — the dispatcher is the contract. The OCR fallback is a branch inside the PDF adapter, not a separate adapter.

**Depth note:** Every format-specific weirdness — paragraph reconstruction from PDF character blocks, `python-docx` quirks, OCR threshold tuning, YAKE blocklist — concentrates here. Deletion test: indexer workers, candidate-failure detection, and the upload-edge encrypted-PDF rejection would each re-derive format probing.

---

### `core/chunk`

**Interface:**

```python
@dataclass(frozen=True)
class Chunk:
    body_text: str
    is_headline: bool
    chunk_seq: int

def chunk(doc: ExtractedDoc) -> list[Chunk]
def headline_chunk(title: str, abstract: str) -> Chunk
def headline_fingerprint(title: str, abstract: str) -> str  # stable hash
```

Invariants: ADR-0002 token budget respected; paragraph boundaries preferred (ADR-0001 §3); mid-paragraph splits only for oversized paragraphs. `chunk_seq` is 0 for headline, 1..n for body. `headline_fingerprint` is a stable normalized hash of `(title, abstract)` used by the publish gate.

**Responsibilities:** Sole owner of the body-splitting heuristic and the headline-chunk projection. Owns `headline_fingerprint` because the publish gate, post-publish edit reindex, and worker chunk-write all compare against the same canonical form.

**Seams:** None. One splitter, called by `core/jobs` task bodies (initial index + headline reindex) and by `core/documents.publish` (to compute the fingerprint of staged metadata for the gate check).

**Depth note:** Without isolation, the paragraph-boundary heuristic and the fingerprint hash would diverge between the indexing path and the publish gate — exactly the bug ADR-0007 §9 / ADR-0010 §4's gate guards against. Deletion test: re-implementations in `core/jobs` and `core/documents` would silently disagree on fingerprint formatting.

---

### `core/jobs`

**Interface:** Per ADR-0008 §3, typed enqueue helpers + Procrastinate task definitions:

```python
# enqueue (caller-facing)
async def enqueue_index_document(version_id: int) -> None
async def enqueue_ocr_index_document(version_id: int) -> None
async def enqueue_refresh_headline(version_id: int) -> None
async def enqueue_purge_deleted() -> None
async def enqueue_sweep_orphan_blobs() -> None

# task bodies (worker-facing, not imported by feature code)
@task(queue="default", retry=...)
async def index_document(version_id: int): ...
@task(queue="ocr", retry=..., concurrency=1)
async def ocr_index_document(version_id: int): ...
@task(queue="default", retry=...)
async def refresh_headline(version_id: int): ...
```

Invariants: enqueues use `queueing_lock` keyed per ADR-0008 §7 (`index:v{id}`, `headline:v{id}`, `maintenance:purge`, `maintenance:orphan`); execution `lock` matches; request-time enqueues defer through the active SQLAlchemy transaction's psycopg connection so domain row + job commit together (§1); `AlreadyEnqueued` is a no-op.

**Task body for `index_document` (canonical orchestration):**

```python
async def index_document(version_id: int) -> None:
    version = await documents._begin_indexing(version_id)
    if version is None:              # already completed retry
        return
    try:
        doc = await extract(version.sha256, version.mime)
    except OCRRequired:
        await enqueue_ocr_index_document(version_id)
        return
    except (PDFSyntaxError, BadZipFile, ...) as e:
        await documents.mark_failed(version_id, f"corrupted: {type(e).__name__}")
        return
    await _complete_indexing(version, doc)
```

`ocr_index_document` obtains the same locked start/no-op decision and calls the same private `_complete_indexing` helper after it runs `ocrmypdf` before `extract`. `refresh_headline` reads the candidate's persisted title/abstract, re-embeds the headline only, and calls `documents.write_headline(version_id, headline, embed, fp)`.

**Responsibilities:** Defines every async edge (task names, queues, retry policy from ADR-0008 §5, locks, periodic defers). Owns side-effect orchestration: extract → chunk → embed → persist call. Owns the OCR re-enqueue branch. Never opens transactions or writes domain rows directly — every persist goes through a `core/documents` function so DB invariants stay in one place.

**Seams:** None. Procrastinate is treated as an external boundary (like Authlib in `core/auth`); switching it out is post-MVP. Feature code never imports `procrastinate` (ADR-0008 §3).

**Depth note:** The single concentration point for "what async work exists and how it retries." Deletion test: queueing-lock keys, retry policies, and the OCR-handoff branch would scatter into per-feature ad-hoc tasks (ADR-0008 §3 explicitly forbids).

---

### `core/documents`

**Interface:** Single domain chokepoint per PRD §"Implementation Decisions". All DB mutations on `documents`, `document_versions`, `document_authors`, `document_attachments`, and the version-scoped `chunks` rows flow through here.

```python
# Author-facing (called by api/documents under require_authenticated + manageable check)

async def create_draft(
    user_ctx: UserCtx,
    *,
    title: str,
    area_path: str,
    document_type: str,
    visibility: Literal["publico", "interno", "privado"],
    external_authors: list[str],
    coauthor_user_ids: list[int],
) -> DocId
# - Inserts documents (publication_status='draft'),
# - Inserts document_authors: 1 owner + N pending registered + M external.
# - No version row yet.

async def attach_main_version(
    user_ctx: UserCtx,
    doc_id: DocId,
    blob: BlobPutResult,
    *,
    original_filename: str,
) -> VersionId
# - Inserts document_versions (index_status='pending', is_current=false).
# - Enqueues index_document(version_id) inside the same transaction (ADR-0008 §1).

async def update_draft_metadata(
    user_ctx: UserCtx,
    doc_id: DocId,
    *,
    title: str | None = None,
    abstract: str | None = None,
    keywords: list[str] | None = None,
    fecha: date | None = None,
    visibility: Literal[...] | None = None,
    area_path: str | None = None,
    document_type: str | None = None,
) -> None
# - Writes through to documents.* for top-level fields.
# - Writes staged_abstract/keywords/fecha on the candidate document_versions row.
# - If title or abstract changed, enqueues refresh_headline(version_id).

async def publish(user_ctx: UserCtx, doc_id: DocId) -> None
# - Loads candidate version; recomputes headline_fingerprint from current
#   documents.title + staged_abstract; raises PublishConflict (→ 409) if
#   index_status != 'indexed' OR fingerprint != stored headline_fingerprint.
# - Atomic SQL transaction (ADR-0006 §6): flips chunks.is_current,
#   document_versions.is_current, sets documents.publication_status='published'.
# - Copies staged_* into documents.abstract/keywords/fecha.
# - Enqueues fan_out_coauthor_invites (PRD #5 retrofits the send).

async def add_attachment(
    user_ctx: UserCtx,
    doc_id: DocId,
    blob: BlobPutResult,
    *,
    original_filename: str,
) -> AttachmentId
# - Enforces 5-attachment cap transactionally (ADR-0006 §7).

async def remove_attachment(user_ctx: UserCtx, doc_id: DocId, att_id: AttachmentId) -> None

async def get_draft_state(user_ctx: UserCtx, doc_id: DocId) -> DraftState
# Returns the polling payload: index_status, staged_*, headline_fingerprint_match,
# publish_gate_reason ('processing' | 'reindexing_headline' | 'processing_failed' | None),
# index_error. publish_gate_reason is None iff the publish call would succeed.

async def list_own_documents(user_ctx: UserCtx) -> list[OwnDocSummary]
# For /mis-trabajos. Owner + accepted-coauthor scope via manageable_where.

# Worker-facing (called by core/jobs task bodies; never by api/*)

async def load_candidate(version_id: int) -> CandidateVersion
async def write_indexed_candidate(
    version_id: int,
    body: list[Chunk],
    headline: Chunk,
    embeds: list[halfvec],
    meta: IndexableMetadata,
    headline_fingerprint: str,
) -> None
# Single transaction: inserts chunks (is_current=false, version_id=this),
# sets document_versions.index_status='indexed', staged_*, headline_fingerprint, indexed_at.

async def write_headline(version_id: int, headline: Chunk, embed: halfvec, fp: str) -> None
# Used by refresh_headline. Replaces the single is_headline=true chunk for this
# version while retaining its is_current value: a published-current refresh
# remains searchable; a staged replacement remains unsearchable.

async def mark_failed(version_id: int, error: str) -> None
# Transaction: index_status='failed', index_error=error,
# inserts notifications(kind='processing_failed', user_id=owner, ...) with unique event_key.
```

Private worker collaboration: `_begin_indexing(version_id)` row-locks the version, returns `None` for an already `indexed` completion, and otherwise moves the task into `processing` before extraction/OCR side effects. It is shared by default and OCR task implementations, not an enqueue Interface.

Invariants: every author-facing function takes `user_ctx` and applies `document_access.manageable_where` (owner | accepted) before any mutation; cross-user attempts return 404 (ADR-0010 §7). `publish` is the only function that writes to `documents.publication_status` or makes replacement chunks searchable. Chunks are keyed by `(version_id, chunk_seq)`, so current and candidate versions can both hold headline/body sequences; exactly the current version's chunks carry `is_current=true`. The 5-attachment cap, the headline-fingerprint check, the completed-indexing no-op transition, and the atomic publish SQL (ADR-0006 §6) are not exposed as building blocks. No worker function takes `user_ctx` — workers don't have one.

**Responsibilities:** Owns every domain mutation across the four document tables and the version-scoped `chunks` rows. Owns the publish transaction's SQL exactly (ADR-0006 §6). Owns the `processing_failed` notification insert. Owns the "post-publish metadata edits persist immediately + enqueue headline reindex" rule (PRD story 28-29). Owns the `publish_gate_reason` projection — server is the source of truth (PRD §"Implementation Decisions").

**Seams:** None. The PRD locks a single domain module: "core/documents (single domain module per session decision)". Splitting into `core/draft` / `core/version` / `core/attachment` was considered and rejected — the publish transaction, the attachment-cap invariant, and the manageable-by-author predicate would re-cross those boundaries on every call.

**Depth note:** Every lifecycle invariant from ADR-0010 §3-§4 lives here. Deletion test: the atomic publish SQL would scatter into the router; the 5-attachment cap would race under concurrent uploads; the publish-gate reason logic would diverge between the polling endpoint and the publish endpoint (PRD §"Implementation Decisions" — server is source of truth). One module so the gate's source-of-truth is genuinely one place.

---

### `api/documents` (FastAPI router)

**Interface:**

```
POST   /api/documents                                  → create_draft        (require_authenticated)
POST   /api/documents/{id}/upload                      → 202 / 415           (require_authenticated, manageable)
GET    /api/documents/{id}/draft                       → DraftStateDTO       (require_authenticated, manageable)
PATCH  /api/documents/{id}                             → 204                 (require_authenticated, manageable)
POST   /api/documents/{id}/publish                     → 204 / 409           (require_authenticated, manageable, owner-only)
POST   /api/documents/{id}/attachments                 → 201 / 413 / 415     (require_authenticated, manageable)
DELETE /api/documents/{id}/attachments/{att_id}        → 204                 (require_authenticated, manageable)
GET    /api/me/documents                               → list[OwnDocDTO]     (require_authenticated)
```

`POST /upload` is `multipart/form-data` direct to FastAPI (ADR-0004 §8). The route streams into `blob_store.put_stream(max_bytes=50_000_000)`, validates `sniffed_mime` against `{pdf, docx, odt}` (415 on mismatch), calls `extract.probe_encrypted(head_bytes)` for PDFs (415 on `PDFEncryptionError`), then `documents.attach_main_version(...)` and returns `202`. `PublishConflict` from `documents.publish` returns 409. Cross-user manageable check returns 404 to avoid existence leakage.

DTO shapes are ORM-free Pydantic v2 (ADR-0003 §6). `DraftStateDTO` matches the shape of `documents.get_draft_state`.

**Responsibilities:** HTTP / URL contract layer. Streams uploads through `blob_store`, performs the sync MIME + encrypted-PDF gate, shapes DTOs. Never opens transactions, never writes `documents`/`document_versions`/`document_authors`/`document_attachments` directly. Owns the `multipart` parsing and the synchronous 415 responses (PRD §"Implementation Decisions").

**Seams:** None. The eight endpoints share the same auth dep set and the same `core/documents` chokepoint; PRD-2's "earn extraction with a second caller" rule keeps them collocated.

**Depth note:** Thin by design — the policy bundle (publish gate, attachment cap, fingerprint check, manageable predicate) lives in `core/documents`. Deletion test for the router alone: trivial; for the upload route's MIME + encrypted gate: those guard `core/documents` against having to know about format-specific bytes. Keeping them at the edge preserves `core/documents` as pure DB logic.

---

### `app/mis-trabajos/page.tsx` (Next.js client page)

**Interface:** Renders at `/mis-trabajos`. Reads `useUser()`; on invitado, `router.replace("/login?next=/mis-trabajos")`. Fetches `GET /api/me/documents` via TanStack Query. Renders two sections: **Borradores** (publication_status='draft') and **Publicados**, each row linking to `/mis-trabajos/{id}/editar`. Header has a primary CTA to `/mis-trabajos/nuevo`. No SSR (ADR-0004 §3, PRD §"Out of Scope").

**Responsibilities:** Owner-scoped list, invitado guard, entry-point CTA.

**Seams:** None.

**Depth note:** Thin but earns its own page because the invitado redirect, the two-section layout, and the empty state ("Aún no subiste ningún trabajo — empezá con Nuevo trabajo") are the management-surface contract and need Playwright coverage independent of the draft form.

---

### `app/mis-trabajos/nuevo/page.tsx`

**Interface:** Single-step form (PRD story 4). RHF + Zod (ADR-0004 §8). Fields:

- `titulo` — required text.
- `area_path` — `AreasCascader` with `requireLeaf` (PRD story 5).
- `tipo` — select over the closed enum (PRD story 6).
- `visibilidad` — three-radio with inline copy per option (PRD story 7).
- `external_authors` — free-text, comma-or-line-separated (PRD story 8).
- `coauthor_user_ids` — `CoauthorPicker` (PRD story 9).
- `main_file` — `<input type="file" accept=".pdf,.docx,.odt">` (PRD story 11).

On submit: `POST /api/documents` (validation 422 surfaced inline) → on success, `POST /api/documents/{id}/upload` with the file (415 surfaced inline for encrypted-PDF / wrong mime, 413 for >50 MB) → on 202, `router.replace("/mis-trabajos/{id}/editar")`.

**Responsibilities:** Form schema (Zod), two-request submit orchestration, inline error rendering for the synchronous failure paths. Composes `AreasCascader({ requireLeaf: true })`, `CoauthorPicker`, the file picker.

**Seams:** None.

**Depth note:** Single concentration of "what a draft looks like before it has any candidate version." Deletion test: scatter the two-request submit and the 415-vs-413-vs-422 routing across reusable subcomponents and the error-recovery UX gets inconsistent.

---

### `app/mis-trabajos/[id]/editar/page.tsx`

**Interface:** Edit page. Composes:

- `useDraftState(id)` for the polled server state (status pill, publish-gate reason).
- A metadata form (RHF + Zod, scoped to this page — not extracted) bound to `documents.get_draft_state`'s staged + author-entered fields. Save-on-blur PATCHes `/api/documents/{id}`.
- A suggestions panel that renders `staged_abstract`, `staged_keywords`, `staged_fecha` next to the editable inputs (PRD stories 17-18). While `index_status='processing'`, the panel shows a spinner over the suggestion slots.
- `AttachmentsPanel({ docId })` (PRD stories 22-25).
- **Publish** button — disabled iff `publish_gate_reason !== null`. The inline message under the button echoes the server's `publish_gate_reason` (one of: `Procesando…`, `Reindexando título…`, `Falló el procesamiento — revisá tu archivo`). On click: `POST /api/documents/{id}/publish`; a 409 (race) re-renders the gate reason from the next poll.
- Status pill at the top: `Procesando…` / `Listo para publicar` / `Falló el procesamiento` (PRD story 16).

**Responsibilities:** The edit-page layout, the save-on-blur metadata PATCH wiring, the publish-button gating, the suggestions↔staged↔final flow. Never derives the gate reason locally — it renders the server value verbatim (PRD §"Implementation Decisions" — server is source of truth).

**Seams:** None.

**Depth note:** Where every PRD UX rule that connects "what the worker did" to "what the user is allowed to click" lives. Deletion test: scattering the publish-gate render, the save-on-blur PATCH, and the suggestions panel into separate pages would force each to re-derive the polling cadence and the gate-reason copy.

---

### `app/mis-trabajos/useDraftState.ts`

**Interface:** `useDraftState(docId: number) -> { state: DraftStateDTO | undefined, isLoading: boolean, isError: boolean }`.

TanStack Query against `GET /api/documents/{id}/draft`. `refetchInterval`: 3000 ms while `state.index_status === 'processing'` OR `state.publish_gate_reason === 'reindexing_headline'`; `false` otherwise (idle while `indexed` and fingerprint-matched, or while `failed`). Query key `["draft", docId]`. Mapped 404 → `isError`.

**Responsibilities:** Polling cadence, request shape, query-key design. Single concentration of "when do we poll vs. idle."

**Seams:** None.

**Depth note:** Earns isolation because the cadence rule (poll while `processing` or `reindexing_headline`, idle otherwise) is non-obvious and would silently drift if every page that needs draft state copied the `refetchInterval` expression. Deletion test: future surfaces (a global "in-progress drafts" badge in `AuthNav`?) would each reinvent the rule.

---

### `components/CoauthorPicker.tsx`

**Interface:** Props: `{ value: number[], onChange(ids: number[]) }`. Renders a typeahead input that debounces `GET /api/users/search?q=...` (returns up to ~10 matches: `{ user_id, name, email_local, picture_url }`). Selected entries appear as removable chips. Excludes the current user from results.

**Responsibilities:** User-search request shape, debounce, chip render, value plumbing. Does not know about `document_authors` rows — the parent form passes `value` to `POST /api/documents` and the backend writes `pending` rows.

**Seams:** None.

**Depth note:** Single visual contract for "pick a registered UNSAM user." Deletion test borderline — one caller at MVP (the `/nuevo` form) — but PRD #5's coauthor-invite re-add flow will reuse it, and the typeahead debounce + exclude-self rules are non-trivial enough that a Playwright spec wants a stable component to target.

---

### `components/AttachmentsPanel.tsx`

**Interface:** Props: `{ docId: number, canManage: boolean }`. Reads attachments from `GET /api/documents/{id}/draft` (server includes the list there) and renders:

- Existing rows: `original_filename · sizebytes` + "Quitar" button (PRD stories 24-25). Click → `DELETE /api/documents/{docId}/attachments/{att_id}` → optimistic remove.
- Add affordance: `<input type="file" accept=".csv,.json,.txt,.py,.ipynb,.png,.jpg,.jpeg,.gif,.zip">` (ADR-0006 §10 allowlist). Click → `POST /api/documents/{docId}/attachments` with the file. Disabled when `attachments.length === 5` with copy "Llegaste al máximo de 5 adjuntos" (PRD story 23). 413 surfaced inline as "Este adjunto pasa los 20 MB. Probá uno más chico."

`canManage` is true for owner + accepted coauthors per ADR-0010 §8 — the page passes whatever the server exposes; this component just hides the add/remove affordances when false.

**Responsibilities:** Attachment list + add + remove UX, including the 5-cap disable rule and the 20 MB inline error. Owns the optimistic-remove pattern.

**Seams:** None.

**Depth note:** The 5-cap and the 20 MB limit are user-visible invariants (PRD stories 22-23) — concentrating them here keeps the error copy and the disabled-state rule from drifting between the edit page and any future surface that lists attachments.

---

## Touched, not new

- **`core/document_access`** — gains `manageable_where(alias: str, user_ctx: UserCtx) -> tuple[str, dict]` returning the WHERE-clause body for owner-or-accepted-coauthor scope (ADR-0010 §8). Joins `document_authors` with `status IN ('owner', 'accepted') AND user_id = :user_id`. Used by every `api/documents` mutation route and by `list_own_documents`. The seam now has **three real adapters** (`invitado_where`, `readable_where`, `manageable_where`); the conceptual seam flagged in auth-sessions.md is now fully materialized.
- **`api/auth`** — adds `GET /api/users/search?q=<prefix>` guarded by `require_authenticated`. Returns up to ~10 `{user_id, name, email_local, picture_url}` rows from `users` with `ILIKE` prefix on `name` (and possibly `email_local`), excluding the current user. SQL inline in the router per the same "earn a domain module with a second caller" rule that keeps notifications inline.
- **`components/AreasCascader`** — gains `requireLeaf?: boolean` prop (PRD story 5). When `true`, the cascader's emitted `onChange` only fires after Materia (the leaf) is selected; partial selections render an inline error "Elegí una Materia". Other callers (the search filter) keep `requireLeaf={false}`.
- **`chunks` schema** — `version_id bigint not null references document_versions(id)` and `is_current boolean not null default false` implement ADR-0006 §6. Sequence identity is version-scoped: `UNIQUE (version_id, chunk_seq)` replaces `UNIQUE (doc_id, chunk_seq)`, permitting an indexed replacement to coexist with the current version before publish.
- **`AuthNav`** — gains a "Mis trabajos" entry in the authenticated dropdown linking to `/mis-trabajos`. One line.
- **`api/search` / `core/search_query`** — unchanged at the public interface; lexical, hybrid-semantic, and `recientes&q=` candidate CTEs now admit only `chunks.is_current=true`. Publish is the atomic point at which replacement text enters reader-visible search.

## Dependency graph

```
                            app/mis-trabajos/page.tsx
                                       |
                              GET /api/me/documents
                                       |
                            ┌──────────┴──────────┐
                            |                     |
            app/mis-trabajos/nuevo/page.tsx       app/mis-trabajos/[id]/editar/page.tsx
                            |                          /        |          \
                  AreasCascader (requireLeaf)   useDraftState  metadata  AttachmentsPanel
                  CoauthorPicker                     |          form           |
                  file picker                  GET /api/documents/{id}/draft
                            |                                                  |
                  POST /api/documents                                           |
                  POST /api/documents/{id}/upload         POST/DELETE /api/documents/{id}/attachments
                  GET  /api/users/search                  POST /api/documents/{id}/publish
                            |                             PATCH /api/documents/{id}
                            |                                                  |
                            └─────────────────────┬────────────────────────────┘
                                                  |
                                             api/documents
                                                  |
                                          core/documents  ────────────► core/document_access.manageable_where
                                                  |
                                          (Postgres: documents,
                                           document_versions,
                                           document_authors,
                                           document_attachments,
                                           chunks)
                                                  |
                                                  |◄──── enqueue (transactional, ADR-0008 §1)
                                                  |
                                              core/jobs ─── index_document task ───► core/extract ──► core/chunk ──► core/embed
                                                  |                  |                       |
                                                  |                  └─ on OCRRequired ─► ocr queue (ocr_index_document)
                                                  |                  └─ on parse fail  ─► core/documents.mark_failed
                                                  |                  └─ on success     ─► core/documents.write_indexed_candidate
                                                  |
                                              refresh_headline task ──► core/chunk.headline_chunk ──► core/embed
                                                                              └────► core/documents.write_headline

  (upload edge — synchronous)
                  POST /api/documents/{id}/upload
                            |
                  core/blob_store.put_stream  (MIME sniff, max 50 MB, atomic write + dedup)
                            |
                  core/extract.probe_encrypted  (PDF only; raises → 415)
                            |
                  core/documents.attach_main_version  (enqueues index_document in same txn)
                            |
                  202 Accepted

  (download — out of scope this PRD, lands in PRD #4)
                  GET /api/docs/{id}/download → core/document_access.readable_where → core/blob_store.internal_path → X-Accel-Redirect
```

No cycles. `core/jobs` task bodies depend on `core/documents`, `core/extract`, `core/chunk`, `core/embed`; none of those depend on `core/jobs` (enqueue helpers are called by `core/documents` and `api/*`, not by other `core/*` modules). `api/documents` depends on `core/documents` and `core/blob_store`; `core/documents` depends on `core/document_access` and `core/jobs` (for enqueue). Frontend talks to FastAPI only through the typed OpenAPI client (ADR-0004 §6); no Server Components on `/mis-trabajos*` (ADR-0004 §3, PRD §"Out of Scope").

## Out of scope

- **Coauthor invitation send / accept / decline** — PRD #5. `create_draft` writes `document_authors` rows with `status='pending'`; PRD #5 owns the notification fan-out and the pending → accepted transition. The `enqueue_fan_out_coauthor_invites` helper exists in `core/jobs` (ADR-0008 §3) but is a no-op stub at this PRD's window; PRD #5 fills the task body and retrofits invites for any pending rows created here.
- **Main-file replacement** — PRD #6. No `PUT`/replace endpoint on `/api/documents/{id}/upload`. If the user uploaded the wrong file pre-publish, the only recovery before PRD #7 lands is operator-side; PRD #25 ships v1 only.
- **Author soft-delete, restore, 180-day purge** — PRD #7. The `documents.soft_deleted_at` column exists (ADR-0006 §5) but no endpoint writes it in this PRD. `enqueue_purge_deleted` is registered but the periodic defer is gated until PRD #7 (or behind a feature flag at MVP per ADR-0008 §9).
- **Download endpoints** (`GET /api/docs/{id}/download`, `GET /api/docs/{id}/attachments/{att_id}`) — PRD #4. ADR-0006 §8 defines them; PRD #25 only writes the rows they read.
- **Detail page** (`/docs/[id]`) — PRD #4. Publish makes the document readable; the public-facing surface lands in PRD #4.
- **Moderation reporting / hide / unhide** — PRD #8. The `moderation_hidden_at` column exists (ADR-0010 §10) and `readable_where` already filters on it; no producer here.
- **Server Components for `/mis-trabajos`** — explicitly rejected by ADR-0004 §3 + ADR-0005 §12. Client-only.
- **`core/draft` / `core/version` / `core/attachment` split** — rejected. PRD locks single `core/documents` chokepoint; splitting would force the publish transaction, the 5-attachment cap, and the manageable predicate to re-cross module boundaries on every call.
- **`api/attachments` separate router** — rejected. Two endpoints, both document-scoped, share the same `manageable` dep; collocating with `api/documents` matches the auth-sessions.md "earn extraction with a second caller" rule.
- **`api/users` separate router** — rejected. One read endpoint (`/api/users/search`) that already shares `require_authenticated` with the rest of `api/auth`; promotion to its own router waits for a second user-related endpoint (profile edit, etc.).
- **`core/notifications` domain module** — still rejected (auth-sessions.md out-of-scope). `core/documents.mark_failed` inserts the `processing_failed` notification inline; the existing inline SQL pattern in `api/notifications` is unchanged.
- **Inline "replace" of staged metadata back to the extractor's suggestion** — not surfaced in MVP. The user edits the field; if they want the suggestion back, they re-read it from the suggestions panel. PRD doesn't require a "revert to suggestion" button.
- **`MIN_SEMANTIC_SIMILARITY` recalibration** — unchanged from search-mvp.md; committed fixture only.
- **OCR'ing embedded images inside DOCX/ODT** — ADR-0007 §5; explicitly out.
- **Real Tesseract in unit tests** — ADR-0007 + PRD §"Testing Decisions"; one `ocr_slow`-marked integration test covers the OCR worker invocation.
- **Malware scanning on attachments** — ADR-0006 §10; out.
- **Background-task version of upload (FastAPI `BackgroundTasks`)** — ADR-0003 §4 explicitly bans; the index pipeline goes through `core/jobs` only.

## Further Notes

- Migration `0010` introduces version/chunk columns and backfills existing search rows; follow-up migration `0013` makes `chunks.version_id` mandatory and replaces document-scoped chunk sequence uniqueness with version-scoped uniqueness. Any legacy unversioned rows encountered during that upgrade are assigned a synthetic current indexed version before the constraint is tightened.
- The publish transaction (`core/documents.publish`) is the single SQL block from ADR-0006 §6, run inside one `async with session.begin()` so a crash between flips cannot leave the document partially published (PRD story 37).
- `write_headline` retains the target version's `is_current` flag. A refresh of the published current version updates searchable headline content; a refresh of an indexed candidate cannot expose it before publish.
- `headline_fingerprint` is a stable hash (e.g., `sha256(normalize(title) + "\x00" + normalize(abstract))[:32]`) so the publish gate, the post-edit reindex enqueue rule, and the worker can all compute the same value without coordination. `core/chunk.headline_fingerprint` is the single source.
- `publish_gate_reason` enum values are server-owned: `null` (publishable), `processing`, `reindexing_headline`, `processing_failed`. The frontend maps each to the Spanish copy from the PRD; the server doesn't return user-facing strings.
- The `processing_failed` notification's `event_key` is `processing_failed:{version_id}` to use the existing unique index (ADR-0010 §9) — retries cannot create duplicates (PRD §"MVP acceptance tests" via ADR-0010 §12).
- ADR-0006 §10's MIME sniff happens inside `core/blob_store.put_stream` (bytes are streaming through there anyway); the upload route compares `BlobPutResult.sniffed_mime` against the main-file allowlist after the put completes and returns 415 + an inline message (encrypted PDF gets its own 415 message via `core/extract.probe_encrypted` checked before `put_stream`, so the blob is never written for an encrypted PDF).
