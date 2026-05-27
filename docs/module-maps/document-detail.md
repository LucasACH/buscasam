# Module Map: Document detail and trabajos relacionados

## Source

PRD: [Issue #42 — Document detail page and trabajos relacionados](https://github.com/LucasACH/buscasam/issues/42).

Implements the `/docs/[id]` slice end-to-end: permalink reader page, metadata block, archivo principal + adjuntos rows with X-Accel-Redirect downloads, owner/coautor-only Editar entry-point and Versiones anteriores panel, and a Trabajos relacionados rail driven by headline-to-headline cosine. Lands the `core/related` chokepoint and the reader-side `api/docs` router. Reuses the access policy locked in ADR-0010 §6-§8; introduces no new access adapter.

## Modules

### `core/related`

**Interface:**

```python
@dataclass(frozen=True)
class RelatedRow:
    doc_id: int
    titulo: str
    autores: list[AuthorDisplay]   # display_name + optional user_id
    area_path: str
    tipo: str
    fecha: date | None
    similarity: float              # float in [MIN_SEMANTIC_SIMILARITY, 1.0]

async def fetch_related(
    session: AsyncSession,
    doc_id: int,
    user_ctx: UserCtx,
    *,
    k: int = 5,
) -> list[RelatedRow] | None
```

Invariants: returns `None` iff the requester cannot read the source document under `readable_where` — the same 404-shaped signal `get_detail` returns. Returns `[]` if the source is readable but has no `is_headline=true AND is_current=true` chunk (unpublished candidate-only state, headline reindex mid-flight, or a doc that pre-dates the headline rule), so the rail hides without leaking. Otherwise runs cosine over every `is_headline=true AND is_current=true` chunk across all documents, applies `readable_where` to candidates with the caller's `user_ctx`, drops rows below `MIN_SEMANTIC_SIMILARITY` (reused as-is from search calibration; ADR-0002 §7), excludes the source `doc_id`, and caps at `k=5`. The autores list is loaded only for the survivors, in author-display order. SQLAlchemy/asyncpg errors propagate; no business exceptions.

**Responsibilities:** Sole owner of "readable headline-cosine retrieval." Owns the SQL that loads the source headline embedding only after the source passes `readable_where` (ADR-0010 §6, PRD story 33), the cosine join over `chunks` filtered to `is_headline=true AND is_current=true`, the candidate-side `readable_where` application, the `MIN_SEMANTIC_SIMILARITY` floor, the cap, the source-exclusion `WHERE doc_id <> :source_id`, and the per-survivor authors fetch. Owns the "no headline yet → empty rail" branch.

**Seams:** None at MVP. Access policy is supplied by `core/document_access.readable_where` — this module is its third real caller (after `core/search_query` and `core/documents.get_detail`). A second similarity backend is out of MVP scope.

**Depth note:** Five invariants stack here — source-after-access (security), headline-existence gate (no-leak under candidate-only states), candidate access predicate (no-leak rule), similarity floor (relevance contract), source exclusion (no self-loop). ADR-0010 §6 makes the source-after-access ordering security-load-bearing: any inline implementation in the router would risk loading the source headline before the access check. Deletion test: the router would otherwise re-derive the five-rule SQL, with the access-ordering bug being the one that ships silently.

---

### `core/documents` — touched, adds `get_detail`

**New surface:**

```python
@dataclass(frozen=True)
class DetailVersion:
    n: int                        # 1-based version sequence
    original_filename: str
    mime: str
    size_bytes: int
    indexed_at: datetime | None
    is_current: bool

@dataclass(frozen=True)
class DetailRow:
    doc_id: int
    titulo: str
    autores: list[AuthorDisplay]
    area_path: str
    tipo: str
    fecha: date | None
    visibility: Literal["publico", "interno", "privado"]
    abstract: str
    palabras_clave: list[str]
    archivo_principal: MainFile   # original_filename, size_bytes, mime
    adjuntos: list[Attachment]    # up to 5 rows
    versions: list[DetailVersion] | None   # populated iff manageable
    manageable: bool

async def get_detail(
    session: AsyncSession,
    doc_id: int,
    user_ctx: UserCtx,
) -> DetailRow | None
```

Invariants: returns `None` when the source fails `readable_where(user_ctx)` — the router maps `None → 404` uniformly. `archivo_principal` and `adjuntos` always reflect the published current version's rows (PRD story 13); a mid-flight indexed candidate never replaces them. `versions` and `manageable=true` are populated exclusively when `manageable_where(user_ctx)` admits the requester (owner or accepted coautor); for any other reader `manageable=false` and `versions` is omitted from the DTO. The autores list includes both registered and external attribution rows in `document_authors` order; external rows carry `display_name` only (no `user_id`, no login affordance — PRD story 11). No mutations.

**Responsibilities:** The single SELECT-bundle for the detail payload. Owns the join across `documents + document_versions (current) + document_authors + document_attachments`, the optional `document_versions (all)` subquery for the manager branch, and the readable/manageable predicate split. Does not call `core/related` — the detail and related endpoints are two round-trips by design (PRD §"Implementation Decisions").

**Seams:** None added by this PRD. The existing publish/draft transaction surface is untouched.

**Depth note:** The detail read shares its join shape and `is_current` invariants with the publish transaction already owned here; co-locating prevents the `is_current` rule from drifting between writers and the reader. Deletion test: `api/docs` would inline the four-table join and the manager-branch conditional, with the manager-only `versions` field becoming a likely leak surface.

---

### `api/docs` (FastAPI router)

**Interface:**

```
GET /api/docs/{id}                                  → DetailDTO          (200) | 404
GET /api/docs/{id}/related                          → RelatedDTO[]       (200) | 404
GET /api/docs/{id}/download                         → X-Accel-Redirect   (200) | 404
GET /api/docs/{id}/attachments/{att_id}             → X-Accel-Redirect   (200) | 404
GET /api/docs/{id}/versions/{n}/download            → X-Accel-Redirect   (200) | 404
```

All five endpoints accept invitado and authenticated requests; the route dependency builds `UserCtx` from the session cookie (absent → invitado). All denial paths return a uniform `404` with the same Spanish empty body envelope — no role hint, no login nudge, no existence leak. The detail and related endpoints use `core/documents.get_detail` / `core/related.fetch_related` (both already encapsulate `readable_where`); main-file and attachment download routes call `readable_where` directly (or via a small helper) before reaching into `documents.archivo_principal_sha256(doc_id)` / `documents.attachment_sha256(doc_id, att_id)`; the historical-version download uses `manageable_where` because non-current versions are author-only (PRD story 26). All download responses stream via nginx `X-Accel-Redirect` through `core/blob_store.internal_path(sha256)` and set the `Content-Disposition` filename from the row's `original_filename` and `Content-Type` from its recorded MIME (PRD story 27, ADR-0006 §8-§9). FastAPI workers never read blob bytes. DTOs are ORM-free Pydantic v2 (ADR-0003 §6); `versions` and `manageable=true` are *omitted* (not null) on non-manager responses.

**Responsibilities:** HTTP/URL edge for every reader-facing document route. Streams downloads through `blob_store`. Maps the three "denied" signals — `None` from `get_detail` / `fetch_related`, a `readable_where`/`manageable_where` miss on the download SQL, and a non-existent id — to one indistinguishable 404. Shapes DTOs onto the response. Never opens a transaction; never writes any document table.

**Seams:** None. The five endpoints share auth dep set, predicate set, and the X-Accel-Redirect projection — collocating preserves the uniform-404 contract across them.

**Depth note:** Thin by design — the policy lives in `core/documents` and `core/related`. The router's job is the no-leak 404 envelope. Splitting into `api/docs_detail` / `api/docs_downloads` would force the uniform-404 rule to re-cross files; the readable vs. manageable predicate split would risk drift between the main-download and version-download handlers.

---

### `app/docs/[id]/page.tsx` (Next.js client page)

**Interface:** Renders at `/docs/{id}`. Reads `id` from `useParams`. On `is404` from `useDocDetail`, renders the Spanish empty state (`"No encontramos este documento"`) and stops — does not call `useRelated`. Otherwise composes:

- Metadata block: título, autores (with external attributions rendered as plain text, registered authors as the display-name only at MVP — no profile links yet), área (display name via the áreas tree from `/api/areas`), tipo, fecha, visibilidad badge.
- Abstract and palabras clave.
- Archivo principal row: `<a href="/api/docs/{id}/download" download>` "Descargar".
- Adjuntos list (up to 5): each row `<a href="/api/docs/{id}/attachments/{att_id}" download>` "Descargar".
- "Editar" CTA linking to `/mis-trabajos/{id}/editar` — rendered only when `detail.manageable === true`.
- `<VersionsPanel docId={id} versions={detail.versions} canManage={detail.manageable} />` — the panel itself returns `null` if not `canManage` or if `versions` is absent; the page passes the props unconditionally.
- Trabajos relacionados rail: `useRelated(id).data` mapped onto `ResultCard` (snippet-optional variant — see "Touched, not new"). Rail is hidden entirely when the list is empty (PRD story 19); no header rendered.

The page sets `document.title = detail.titulo` in a `useEffect` (PRD story 31) and reverts on unmount. No SSR (ADR-0004 §3). Mobile reflow: metadata + adjuntos + rail stack vertically below the `md` breakpoint (PRD story 30).

**Responsibilities:** URL → component tree binding. Tab title side-effect. 404 short-circuit. Reflow tokens.

**Seams:** None.

**Depth note:** The single concentration point for the detail page layout and the manager-vs-reader branching. Deletion test: scattering the four conditional panels (Editar, Versions, Related, 404) across child components would lose the page-level guarantee that a non-manager never sees a manager-only affordance.

---

### `app/docs/[id]/useDocDetail.ts` (hook)

**Interface:**

```ts
useDocDetail(docId: number) -> {
  detail: DetailDTO | undefined;
  isLoading: boolean;
  isError: boolean;
  is404: boolean;
}
```

TanStack Query against `GET /api/docs/{id}`. Query key is `["doc-detail", docId]`. `404` responses set `is404=true` and do **not** retry (TanStack Query `retry: (failureCount, err) => err.status !== 404`). All other errors set `isError=true`. `detail.manageable` and `detail.versions` are passed through opaquely — interpretation lives in the page and `VersionsPanel`.

**Responsibilities:** Request shape, query-key derivation, 404 detection without retry.

**Seams:** None.

**Depth note:** Keeps the page a layout. Without it, the 404 retry policy would inline into the page (a common bug surface: the no-retry-on-404 rule is what prevents probing-style refetch loops).

---

### `app/docs/[id]/useRelated.ts` (hook)

**Interface:**

```ts
useRelated(docId: number) -> {
  related: RelatedDTO[] | undefined;
  isLoading: boolean;
  isError: boolean;
}
```

TanStack Query against `GET /api/docs/{id}/related`. Query key is `["doc-related", docId]` — independent from `useDocDetail` so the rail can render its own skeleton while the detail is fetched, and so a detail refetch does not invalidate the rail (PRD §"Implementation Decisions"). A `404` on this endpoint resolves to `related=undefined, isError=true` (the page already rendered the empty state via `useDocDetail`'s `is404`, so this path is degenerate but explicit). Returns `[]` for the "no candidates above floor" case — the page hides the rail without ceremony.

**Responsibilities:** Request shape, query-key derivation.

**Seams:** None.

**Depth note:** Independence from `useDocDetail` is the whole point — earns isolation because that decoupling is the PRD's locked decision, not an implementation detail.

---

### `app/docs/[id]/useVersionDownload.ts` (hook)

**Interface:**

```ts
useVersionDownload(docId: number) -> (n: number) => Promise<void>
```

Returns a callback that triggers a download for version `n` of `docId`. Implementation issues a HEAD against `/api/docs/{docId}/versions/{n}/download` (cheap because nginx still computes `X-Accel-Redirect`); on `404` it surfaces the inline error to the panel via the returned promise (rejection). On `200` it navigates the browser to the URL so the streamed response triggers the native download. Filename and MIME arrive from `Content-Disposition` and `Content-Type` set by the backend (PRD story 27).

**Responsibilities:** URL construction, 404 surfacing for the rare race where a version is removed (or `manageable` revoked) between detail load and click.

**Seams:** None.

**Depth note:** Earns isolation because the HEAD-preflight + navigate pattern is the recovery contract; inlining it in `VersionsPanel` would leak the URL shape and lose the 404 toast. One caller now; PRD #6 (replace flow) will reuse it for the manager-side "download current" affordance.

---

### `components/VersionsPanel.tsx`

**Interface:**

```ts
type Props = {
  docId: number;
  versions: DetailVersion[] | undefined;
  canManage: boolean;
}
```

Returns `null` if `!canManage || versions == null`. Otherwise renders a header "Versiones anteriores" and one row per version (descending by `n`), each showing `v{n} · original_filename · sizebytes · indexed_at` and a "Descargar" button wired to `useVersionDownload(docId)(n)`. The current version (`is_current === true`) is annotated `(actual)` and rendered alongside the historical rows; the PRD does not exclude it from the panel.

**Responsibilities:** Versions list rendering + Spanish copy + per-row download trigger + inline error display on the version-download promise rejection.

**Seams:** None.

**Depth note:** Concentrates the manager-only versions UI. Deletion test: scattering the canManage gate + row layout + per-version download wiring into the page would re-cross the manager-vs-reader boundary the backend already enforces — and would likely surface the historical-version URL shape to non-managers (e.g., a developer adding a feature reuses the row template without the gate). Keeping the gate inside one component file makes the leak surface auditable.

---

## Touched, not new

- **`components/ResultCard`** — snippet block becomes conditional. The DTO prop widens to a union (or the snippet field becomes optional); when `snippet` is `undefined` the snippet block does not render. Search-mvp.md's depth note already anticipated this reuse: *"reused unchanged when PRD-4 lands related-document cards."* The change is one conditional render; no second visual contract introduced. The related rail mounts `ResultCard` directly with a `RelatedDTO`-shaped row (título, autores, área, tipo, fecha — no snippet).
- **`core/document_access`** — no new adapter. `readable_where` gains its third caller (`core/related`, in addition to `core/search_query` and `core/documents.get_detail`). `manageable_where` gains its second consumer chain via the historical-version download route in `api/docs`. The seam introduced in document-publication.md remains at three adapters; the depth comes from caller count, not adapter count.
- **`core/blob_store.internal_path`** — three new callers inside `api/docs` (main download, attachment download, historical-version download). No interface change.
- **`core/documents`** — gains the read-only `get_detail` surface defined above. No change to the publish/draft mutation surface.
- **AuthNav / sidebar** — unchanged. The detail page is reached via search results, related cards, or shared links; it does not introduce a top-nav entry.

## Dependency graph

```
                              app/docs/[id]/page.tsx
                            /         |          |           \
              useDocDetail     useRelated    VersionsPanel    ResultCard (snippet-optional)
                  |                |              |                ↑
                  |                |              └─── useVersionDownload
                  |                |                          |
              GET /api/docs/{id}   GET /api/docs/{id}/related   GET /api/docs/{id}/versions/{n}/download
                  |                |                          |
                  |                |               GET /api/docs/{id}/download
                  |                |               GET /api/docs/{id}/attachments/{att_id}
                  |                |                          |
                  └────────────────┴──────────────────────────┘
                                         |
                                      api/docs
                                    /     |      \
                  core/documents.get_detail    core/related.fetch_related    core/blob_store.internal_path
                                    \     |      /
                            core/document_access.readable_where  (detail, related, main, attachment)
                            core/document_access.manageable_where (historical-version download)
                                          |
                            (Postgres: documents, document_versions,
                             document_authors, document_attachments, chunks)
```

No cycles. Frontend talks to FastAPI only through the typed OpenAPI client (ADR-0004 §6); no Server Components on `/docs/[id]` (ADR-0004 §3, PRD §"Implementation Decisions"). Downloads stream via nginx `X-Accel-Redirect` (ADR-0006 §9), so FastAPI workers are not held by byte streams.

## Out of scope

- **Search results page** — PRD #1.
- **Publication, draft, upload, attachment management, metadata edits** — PRD #25.
- **Main-file replace, promote/demote historical versions, version comparison UI** — PRD #6. This PRD ships read + per-version download for managers only.
- **Moderation report button on the detail page, hide/unhide, moderation inspection of hidden documents** — PRD #8.
- **Sitemap (`/sitemap.xml`)** — deferred to its own slice; ADR-0010 §7 already locks the access predicate.
- **SSR / Open Graph / link-preview meta tags / server-rendered detail for SEO** — deferred. CSR is the explicit decision; revisit if marketing requires social previews.
- **"Compartir" or copy-permalink button** — deferred; URL is the share artifact at MVP.
- **Login nudge on `404` for invitado on interno/privado** — explicitly rejected to preserve the no-leak rule (ADR-0010 §7).
- **Author / área / tipo browse landing pages separate from search** — deferred per `docs/SPEC.md` MVP exclusions.
- **`components/RelatedCard.tsx` as a new component** — rejected. `ResultCard` is reused with snippet optional, honoring search-mvp.md's existing commitment. PRD #42's mention of a new component was overruled by the single-visual-contract rule.
- **A combined `useDetailAndRelated` hook** — rejected. PRD locks two independent TanStack keys so the rail can render its own skeleton.
- **Separate `api/downloads` router** — rejected. The five reader endpoints share predicate set + 404 envelope + X-Accel-Redirect projection; splitting would force those to re-cross files.
- **`core/related` rolled into `core/documents`** — rejected. The source-after-access ordering (ADR-0010 §6, PRD story 33) is security-load-bearing; concentrating it in a dedicated chokepoint keeps the audit surface auditable even with one caller.
- **A separate `MIN_RELATED_SIMILARITY` knob** — rejected per PRD §"Further Notes" to keep one calibration.
- **`core/snippets.py`** — still rejected. The related rail intentionally does not show snippets.
- **`api/users` separate router** — not relevant at this PRD's window (still inside `api/auth` per document-publication.md).
- **Profile links on autores in the detail page** — out at MVP per PRD story 11 (external authors are name-only; registered authors render as plain text at MVP, profile pages are not a slice yet).

## Further Notes

- The 404 envelope is one Spanish string ("No encontramos este documento") served by both the frontend empty state and the backend's response body. The backend can return any small body — the frontend renders its own copy based on the route, not on the response payload.
- `core/related.fetch_related` reads from the same `chunks` rows that `core/search_query` reads (`is_headline=true AND is_current=true`); no schema change. Both modules independently apply `readable_where`, so an HNSW index used by search incidentally accelerates related — but related is not a calibrated retrieval path, just a top-k cosine; no separate index tuning.
- The historical-version download is the first endpoint that consumes a non-current `document_versions` row. The `n` parameter is the 1-based sequence (`row_number()` over `document_versions` ordered by `id` per `doc_id`). The router treats any non-integer or out-of-range `n` as `404` (no 400 — uniform denial).
- `Content-Disposition` filename comes from `document_versions.original_filename` for historical downloads and from the current version's row for `GET /api/docs/{id}/download`; attachments use `document_attachments.original_filename`. The browser sees the human filename even though the on-disk path is the sha256 (PRD story 27, ADR-0006 §3).
- The detail and related endpoints are independent TanStack keys but the page composes both. If the rail's fetch fails (network error, not 404), the page still renders the detail; the rail just shows nothing. No banner.
