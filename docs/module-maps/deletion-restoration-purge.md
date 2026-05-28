# Module Map: Logical deletion, restoration, and purge

## Source

PRD: [Issue #63 — Logical deletion, restoration, and purge](https://github.com/LucasACH/buscasam/issues/63).

Implements the author-owned document lifecycle that sits orthogonal to `publication_status` and `moderation_hidden_at`: the owner deletes a document (immediate reader-invisibility via the inherited access exclusion), recovers it from a **Papelera** for up to 180 días, and — if never restored — has it purged for real by a daily job, with a second daily job reclaiming the now-unreferenced blobs. Extends the chokepoints established in [document-publication.md](document-publication.md) and [version-replacement.md](version-replacement.md). No migration: `soft_deleted_at`, the cascade FKs, and `blob_store.delete` already exist (ADR-0006 §5, §11–12). The entire slice is one predicate, three `core/documents` functions, two periodic jobs, one `blob_store` enumeration method, three endpoints, and the Papelera view.

## Modules

### `core/document_access` — touched, adds `restorable_where`

**New surface:**

```python
def restorable_where(alias: str, user_ctx: UserCtx) -> tuple[str, dict]:
    # WHERE-clause body + bind params selecting the caller's OWN soft-deleted
    # documents. Owner-scoped (status = 'owner' only — NOT the manageable
    # owner|accepted set, because delete/restore are owner-only, PRD stories
    # 18-20) AND soft_deleted_at IS NOT NULL.
    #
    # This is the ONLY predicate in the module that *selects* soft-deleted
    # rows. Every other predicate (invitado_where, readable_where,
    # pending_invitation_disclosure_where, manageable_where) carries
    # `soft_deleted_at IS NULL`. restorable_where is their deliberate inverse.
```

```sql
{alias}.soft_deleted_at IS NOT NULL
AND EXISTS (
  SELECT 1 FROM document_authors da
  WHERE da.doc_id = {alias}.id
    AND da.user_id = :restore_user_id
    AND da.status = 'owner'
)
```

Bind key is distinct (`:restore_user_id`) from `manageable_where`'s `:mgmt_user_id` so a statement can compose both without collision, matching the existing per-predicate bind-key convention.

**Responsibilities:** Owns "what counts as a restorable document" — the single owner-scoped, soft-deleted selection consumed by `restore` and `list_deleted_documents`. The deletion *exclusion* side (every read surface dropping soft-deleted rows) is already owned here via the `soft_deleted_at IS NULL` clause baked into the other predicates (ADR-0010 §6–7); this PRD adds only the inverse.

**Seams:** None. SQL-fragment functions, not adapters — same form as the four existing predicates.

**Depth note:** Deletion test: without `restorable_where`, the "owner + soft-deleted" selection would be hand-written inside both `restore` and `list_deleted_documents`, and the owner-only rule (vs. the laxer manageable `owner|accepted`) could silently drift between the two — exactly the per-surface drift ADR-0010 §6 centralizes here. Concentrating it makes "restorable" one audit surface, symmetric with "readable." It also keeps `core/document_access` the single place a future surface (an undo-toast, an operator Papelera) inherits the rule for free.

---

### `core/documents` — touched, adds `soft_delete` + `restore` + `list_deleted_documents`

**New surface:**

```python
async def soft_delete(
    session: AsyncSession, user_ctx: UserCtx, doc_id: int
) -> None
# - Owner-only via the publish precedent (publish(), documents.py:674): a
#   single SELECT of the document's owner_user_id; if the row is missing or
#   owner_user_id != user_ctx.user_id, raise DocumentNotFound. Accepted
#   coautores and strangers are indistinguishable → 404, no existence leak
#   (PRD stories 18-20). The owner SELECT carries NO moderation_hidden_at and
#   NO soft_deleted_at filter, so a moderation-hidden document is still
#   deletable (story 26) and an already-deleted document still passes the gate
#   (story 13).
# - Stamp-once clock: UPDATE documents SET soft_deleted_at = now()
#     WHERE id = :doc_id AND soft_deleted_at IS NULL.
#   Re-deleting matches zero rows → harmless no-op; the timestamp never moves,
#   so the 180-día window counts from the first deletion (story 14).
# - Touches neither publication_status nor moderation_hidden_at. The lifecycle
#   lives entirely in soft_deleted_at (ADR-0010 §10, ADR-0006 §11).

async def restore(
    session: AsyncSession, user_ctx: UserCtx, doc_id: int
) -> None
# - UPDATE documents SET soft_deleted_at = NULL
#     WHERE id = :doc_id AND ({restorable_where}). Zero rows affected →
#   DocumentNotFound. A live document, a non-owner, or another user's deleted
#   document all resolve to 404 (PRD stories 12, 20).
# - Restores to the exact prior state because delete/restore never mutated
#   publication_status, the current-version flag, attachments, or coautores —
#   they were only hidden by the inherited exclusion. Nothing to reconstruct
#   (stories 8-11).

@dataclass(frozen=True)
class DeletedDocSummary:
    id: int
    title: str
    publication_status: str        # draft | published — for the Papelera label
    soft_deleted_at: datetime
    purge_at: datetime             # soft_deleted_at + 180 días, computed server-side

async def list_deleted_documents(
    session: AsyncSession, user_ctx: UserCtx
) -> list[DeletedDocSummary]
# - Sibling of list_own_documents (documents.py:1080); same shape, gated by
#   restorable_where instead of manageable_where. Returns only the caller's own
#   soft-deleted documents, ordered by soft_deleted_at desc.
# - purge_at is `soft_deleted_at + INTERVAL '180 days'` projected in SQL, so the
#   180-día retention constant is single-sourced server-side; the client derives
#   the days-remaining label by diffing purge_at against now (frontend-projects-
#   labels precedent, version-replacement.md §useDraftState).
```

**Extended surfaces:** None mutated. `list_own_documents` is **unchanged** — `manageable_where` already carries `soft_deleted_at IS NULL`, so a deleted document drops out of the main Mis trabajos list automatically (story 5 inherited, not re-implemented).

Invariants: `core/documents` remains the **sole writer** of `documents.soft_deleted_at` — the stamp-once and owner-only rules cannot drift if no other module writes the column (story 36). An architecture test extends the existing sole-writer rule from version-replacement.md (which already forbids `document_versions` writes outside this module) to cover `soft_deleted_at`.

**Responsibilities:** Owns the soft-delete stamp-once clock, the owner-only gate (publish precedent, raising `DocumentNotFound` for the no-leak 404), the restore clear, and the deleted-documents projection with the server-computed `purge_at`. Sole writer of `soft_deleted_at`.

**Seams:** None added. The owner gate reuses the inline-owner-SELECT pattern from `publish`, not a new abstraction.

**Depth note:** Three invariants concentrate here: stamp-once (window never resets), owner-only-as-404 (no existence leak), and the orthogonality of `soft_deleted_at` to `publication_status`/`moderation_hidden_at`. Deletion test: scatter `soft_delete` into the router and the stamp-once `WHERE soft_deleted_at IS NULL` guard would have to be re-asserted at the HTTP edge, where a double-click race could re-stamp the clock; scatter the owner gate and the no-leak 404 would diverge from the publish precedent. A `core/papelera` split is rejected (see §Out of scope): delete, restore, and the deleted-list all read/write the same `documents` rows and the same `soft_deleted_at` column the rest of `core/documents` owns — splitting would force every call to re-cross the module boundary, the same argument version-replacement.md locks against a `core/candidate` split.

---

### `core/jobs` — touched, adds `purge_deleted` + `sweep_orphan_blobs`

First periodic + advisory-lock code in the module (today it has only request-deferred tasks).

**New surface:**

```python
# Task bodies (procrastinate @app.task, queue="default", retry base 5 min,
# ADR-0008 §5) — thin wrappers that acquire the shared maintenance advisory
# lock and call the testable core.
@app.task(queue="default", retry=_MAINT_RETRY)
async def purge_deleted() -> None: ...
@app.task(queue="default", retry=_MAINT_RETRY)
async def sweep_orphan_blobs() -> None: ...

async def _run_purge_deleted(session: AsyncSession) -> int:
    # DELETE FROM documents WHERE soft_deleted_at < now() - INTERVAL '180 days'.
    # ON DELETE CASCADE collects document_versions, document_attachments, chunks,
    # document_reports, moderation_actions (ADR-0006 §5, §12). In-window and
    # never-deleted documents are untouched. Idempotent: a retried run after a
    # partial commit deletes only rows still matching the predicate. Does NOT
    # delete blobs — the sweep reclaims them once the rows are gone.
    # Returns rowcount for the structured operator log.

async def _run_sweep_orphan_blobs(session: AsyncSession) -> int:
    # async for sha in blob_store.iter_orphan_candidates(min_age=_BLOB_GRACE):
    #     await blob_store.discard_if_unreferenced(session, sha)
    # iter_orphan_candidates yields only blobs past the 24h mtime grace
    # (story 32); discard_if_unreferenced (blob_store.py:104) already does the
    # per-sha "referenced by any live document_versions/document_attachments row?"
    # check and skips a still-referenced sha (story 33). Idempotent: an
    # already-deleted blob unlinks missing_ok; a now-referenced sha is skipped.

async def enqueue_purge_deleted(session: AsyncSession) -> None: ...
async def enqueue_sweep_orphan_blobs(session: AsyncSession) -> None: ...
# Locks maintenance:purge / maintenance:orphan (ADR-0008 §7), AlreadyEnqueued
# → no-op, same _defer_with_savepoint path as the existing helpers.
```

**Periodic registration:** `core/jobs` registers both as daily procrastinate periodic defers on the `default` queue (ADR-0008 §9). Any live worker may defer them; Procrastinate records one defer per period.

**Advisory-lock coordination:** both task bodies wrap their `_run_*` core in one Postgres advisory-lock namespace shared with ADR-0009 backups, so blob deletion cannot race a backup recovery point (ADR-0008 §9, ADR-0006 §13). Two in-scope callers of the lock (purge, sweep) plus the out-of-scope backup job justify a single `_with_maintenance_lock(...)` helper rather than two hand-rolled `pg_advisory_lock` calls.

**Responsibilities:** Owns the two maintenance task bodies, their testable `_run_*` cores (the test surface — `test_jobs_purge_deleted.py` / `test_jobs_sweep_orphan_blobs.py` exercise these directly, not the procrastinate wrapper), the enqueue helpers, the daily periodic registration, and the shared advisory-lock wrapper. The purge SQL and cascade live here; the blob filesystem walk does not (it's `blob_store`'s).

**Seams:** The advisory-lock wrapper is a real seam — two in-scope adapters (purge, sweep) and a third out-of-scope one (ADR-0009 backup). Not a new module; a private helper in `core/jobs`.

**Depth note:** Deletion test: without `_run_purge_deleted` as a chokepoint, the 180-día predicate and the cascade assumptions would live in a task body untestable without a worker; the `_run_*` split is what lets the retention boundary be unit-tested. Without the shared advisory-lock wrapper, purge and sweep would each hand-roll lock acquisition and could drift from the backup namespace, reintroducing the blob/backup race ADR-0006 §13 closes. The periodic registration concentrating in `core/jobs` keeps the "all async entry points are typed helpers here" rule from ADR-0008 §3 intact.

---

### `core/blob_store` — touched, adds `iter_orphan_candidates`

**New surface:**

```python
async def iter_orphan_candidates(*, min_age: timedelta) -> AsyncIterator[str]:
    # Walk the two-level sharded tree under /blobs/ (ab/cd/abcd…); for each
    # stored blob whose final-path mtime is older than `min_age`, yield its
    # sha256 (reconstructed from the shard dirs + filename). Skips /blobs/.tmp/.
    # The 24h mtime grace (story 32) is the `min_age` argument, not baked in.
```

**Surface reused unchanged:** `discard_if_unreferenced(session, sha256)` (blob_store.py:104) already does the per-sha reference check (`UNION ALL` over `document_versions`/`document_attachments`) and the conditional `unlink` — its docstring already names it "the per-sha form of the §12 orphan sweep." The sweep is the batch driver that feeds it; no new reclamation logic is added.

**Responsibilities:** Remains the sole owner of all filesystem IO (ADR-0006 §3). This PRD adds read-side *enumeration* of the sharded tree (with the mtime grace as a parameter) so the orphan sweep never reads the filesystem directly. Reclamation stays on the existing `discard_if_unreferenced` / `delete` surface.

**Seams:** None.

**Depth note:** This is the finding the PRD's "no new core file" line understates: `blob_store` gains no new *file*, but its *interface* grows by one enumeration method. The alternative — `core/jobs` walking `/blobs/` directly — violates the ADR-0006 §3 chokepoint and would fail its architecture test (application blob reads must go through this module; only migrations/tests/container-scripts are exempt). Deletion test: the mtime grace + sha-reconstruction-from-shard-path logic belongs next to `_sharded_path` (blob_store.py:38), which already owns the shard encoding; scattering it into the sweep would duplicate the encoding knowledge in two modules.

---

### `api/documents` — touched, adds three endpoints

**New surface:**

```
DELETE /api/documents/{id}             204 / 404   (require_authenticated, owner-only via core)
POST   /api/documents/{id}/restore     204 / 404   (require_authenticated, owner-only via core)
GET    /api/me/documents/deleted       200 list[DeletedDocDTO]   (require_authenticated)
```

`DELETE /documents/{id}` calls `documents.soft_delete`; `DocumentNotFound → 404`. `POST /documents/{id}/restore` calls `documents.restore`; `DocumentNotFound → 404`. Both return `204` on success, mirroring `POST /publish` (api/documents.py:324). `GET /me/documents/deleted` is the Papelera sibling of `GET /me/documents` (api/documents.py:420), serializing `DeletedDocSummary` (incl. `purge_at`) to `DeletedDocDTO`.

**Responsibilities:** HTTP edge for the three routes. Maps `DocumentNotFound → 404` (the no-leak envelope) and serializes the deleted-list DTO. Never opens transactions beyond the session dependency; never writes `soft_deleted_at`; never gates ownership itself — the owner check lives in `core/documents` (publish precedent), so the router cannot diverge from it.

**Seams:** None. An `api/papelera` router split is rejected (see §Out of scope) — all three routes are document/owner-scoped and reuse the `core/documents` chokepoint, exactly like the existing upload/publish/own-documents routes.

**Depth note:** Thin by design, same as version-replacement.md's `api/documents`. The depth is in `core/documents`; the router's only judgment is the `DocumentNotFound → 404` mapping and the DTO shape.

---

### Frontend Papelera — `app/mis-trabajos/papelera/page.tsx` (new) + `useDeletedDocuments.ts` (new) + Eliminar on the editar page

**New route:** `/mis-trabajos/papelera` — lists the caller's deleted documents (title, original draft/published state, and a "Se elimina en N días" label derived client-side from `purge_at`), each with a **Restaurar** button. Reuses the `OwnDoc`-list rendering pattern from `mis-trabajos/page.tsx` (page.tsx:60). A link from Mis trabajos opens it; it is a sub-route, not a separate nav entry.

**New hook:** `useDeletedDocuments()` — `GET /api/me/documents/deleted` query + a `restore(id)` mutation (`POST /documents/{id}/restore`) that, on success, invalidates both `["me","documents","deleted"]` and `["me","documents"]` so the restored doc reappears in Mis trabajos and leaves the Papelera. Days-remaining is computed in the hook/component by diffing `purge_at` against now; the Spanish label lives on the frontend, the constant does not.

**Eliminar trigger (editar page only):** `app/mis-trabajos/[id]/editar/page.tsx` gains an **Eliminar** affordance (owner-only, alongside Publicar/Reemplazar). The mutation is added to the existing `useDraftState` hook (`softDelete()`, `DELETE /documents/{id}`); on success it invalidates `["me","documents"]` and routes back to `/mis-trabajos`. Mis trabajos list rows stay navigation-only.

**Responsibilities:** The Papelera page is list layout + Restaurar wiring; the editar page adds the Eliminar affordance and forwards owner-ness. Lifecycle interpretation (days-remaining label, mutation invalidation) lives in the hooks, consistent with version-replacement.md.

**Seams:** None.

**Depth note:** `restore` lives in a dedicated `useDeletedDocuments` hook because deleted documents only ever surface in the Papelera, while `softDelete` joins `useDraftState` because Eliminar fires from the editar page where that hook already owns the document's mutations — the two mutations live next to the surface that triggers them. Deletion test: folding the days-remaining label into the page would scatter the `purge_at`-diff in every row; concentrating it in the hook keeps the countdown one place. The Eliminar-on-editar-only decision (PRD-confirmed) keeps the delete mutation wiring single-copy rather than duplicated onto Mis trabajos rows.

---

## Touched, not new

- **`core/documents.list_own_documents`** — **unchanged**. `manageable_where`'s `soft_deleted_at IS NULL` already excludes deleted documents from Mis trabajos (story 5 inherited). Listed here to make explicit that no edit is needed.
- **`core/document_access` exclusion side** — **unchanged**. Búsqueda, detalle, relacionados, descarga, conteos, and the future sitemap inherit the soft-deleted exclusion from the `soft_deleted_at IS NULL` already in `readable_where`/`invitado_where`/`manageable_where` (ADR-0010 §6–7). No per-surface work; covered by the existing `test_document_access_readable.py` + search/detail suites, not re-tested here.
- **OpenAPI / typed client** — regenerated to expose the three new endpoints and `DeletedDocDTO` (incl. `purge_at`). The frontend's typed query/mutation consume them.
- **No migration** — `soft_deleted_at`, the `ON DELETE CASCADE` FKs on `document_versions`/`document_attachments`/`chunks`/`document_reports`/`moderation_actions`, and `blob_store.delete` all already exist (ADR-0006 §5, §11–12). This slice adds no schema.

## Dependency graph

```
                 app/mis-trabajos/page.tsx ──link──► app/mis-trabajos/papelera/page.tsx
                          │                                   │
                          │                            useDeletedDocuments
                          │                              │         │
                 app/mis-trabajos/[id]/editar/page.tsx   │   GET /api/me/documents/deleted
                          │                              │   POST /api/documents/{id}/restore
                    useDraftState (softDelete)           │
                          │                              │
              DELETE /api/documents/{id} ────────────┐   │
                                                      ▼   ▼
                                                api/documents
                                                      │
                                              core/documents
                                ┌──────────────┬──────┴───────────────┐
                          soft_delete       restore          list_deleted_documents
                       (owner gate,         (restorable_where)   (restorable_where)
                        stamp-once)              │                   │
                                                 └─── core/document_access.restorable_where
                                                          (Postgres: documents.soft_deleted_at)

  (daily maintenance — periodic, no request edge)
        core/jobs.purge_deleted ──► _run_purge_deleted
              │                         └─ DELETE ... WHERE soft_deleted_at < now()-180d
              │                            (ON DELETE CASCADE → versions/attachments/
              │                             chunks/reports/moderation_actions)
        core/jobs.sweep_orphan_blobs ──► _run_sweep_orphan_blobs
              │                              └─ blob_store.iter_orphan_candidates(min_age=24h)
              │                                 └─ blob_store.discard_if_unreferenced(sha)
              └─ both wrap _with_maintenance_lock (shared advisory-lock namespace, ADR-0009 backups)
```

No cycles. The request-path endpoints reuse the existing `api/documents → core/documents → core/document_access` graph; the only new edge is `restore`/`list_deleted_documents → restorable_where`. The maintenance jobs add a `core/jobs → core/blob_store` edge (purge → cascade is pure SQL, no module edge). `core/jobs` does not call `core/documents` for purge — the cascade is enforced by the database FKs, so purge is a single `DELETE` with no domain-function detour.

## Out of scope

- **`core/papelera` backend split** — rejected. `soft_delete`, `restore`, and `list_deleted_documents` read/write the same `documents` rows and the same `soft_deleted_at` column `core/documents` already owns; splitting forces every call to re-cross the boundary (same argument version-replacement.md locks against `core/candidate`).
- **`api/papelera` separate router** — rejected. Three document/owner-scoped routes reusing the `core/documents` chokepoint; they belong with the existing document routes.
- **A new predicate for the delete-side owner gate** — rejected. `soft_delete` reuses the inline-owner-SELECT pattern from `publish` (documents.py:674); only the restore/list side needs a predicate (`restorable_where`). Adding a "deletable_where" would duplicate the owner check the publish precedent already inlines.
- **Reusing `manageable_where` for restore** — rejected. `manageable_where` admits accepted coautores and excludes soft-deleted; restore is owner-only and operates *on* soft-deleted rows. The inverse owner-scoped predicate is required.
- **Per-surface exclusion work (búsqueda/detalle/relacionados/descarga/conteos/sitemap)** — out of window. Inherited from the existing `document_access` predicates; covered by `test_document_access_readable.py` and the search/detail suites.
- **Migration** — none. `soft_deleted_at`, cascade FKs, and `blob_store.delete` already exist.
- **Moderation hide/unhide, reports, moderation-access query** — PRD #8. This slice only asserts `moderation_hidden_at` and `soft_deleted_at` are independent and that hiding starts no purge.
- **Pre-purge warning notification** — declined. No deletion notification kind exists at MVP (ADR-0010 §9); purge is silent (story 17).
- **Operator force-purge-now / restore-after-purge surface** — rejected. Purge is the daily job only; no manual trigger, no recovery once purged (backups aside, ADR-0009).
- **Per-version restore** — rejected. Restore operates on the whole document.
- **Eliminar on Mis trabajos list rows** — rejected (PRD-confirmed). Eliminar lives only on the editar page, keeping the delete mutation single-copy.
- **A candidate-abort handshake on deletion** — rejected. A worker indexing an in-flight candidate of a soft-deleted document writes chunks to a version excluded by every read predicate; purge cascades them and the orphan sweep reclaims the blob. The version-replacement.md worker-cancel-by-SQL pattern already covers this; no new signal (story 27).
- **Batch reference-set diff in the sweep** — rejected (PRD-confirmed). The sweep drives `blob_store.discard_if_unreferenced` per past-grace sha rather than computing the referenced set itself, reusing the existing per-sha primitive.

## Further Notes

- `documents.publication_status` and `moderation_hidden_at` are never read or written by delete/restore. A published document that is deleted and restored returns to `published` under its original `visibilidad`; a hidden document can be deleted (the owner gate carries no moderation filter) and its 180-día clock starts at the author's deletion, not the hide (stories 24-26).
- Restore is a true undo with nothing to reconstruct: delete only *hid* the document via the inherited exclusion; the current-version flag, attachments, coautores, and version history were never mutated (stories 8-11).
- `purge_at` is a derived projection (`soft_deleted_at + INTERVAL '180 days'`), not a stored column — so the 180-día constant lives in exactly one place (the SQL projection) and the frontend never holds it.
- The orphan sweep is the *only* path that calls `blob_store.delete` unconditionally; application code abandoning a single blob (rejected upload) still uses `discard_if_unreferenced`. The sweep reuses `discard_if_unreferenced` per sha, so even it never calls the unconditional `delete` directly — it lets the per-sha reference check gate every unlink.
- Purge and the orphan sweep are decoupled in time: purge removes the rows that referenced a blob; the *next* sweep run finds that blob unreferenced (past its grace) and reclaims it. A blob shared by another live document (content-addressed dedup) is skipped by `discard_if_unreferenced` until no row references its sha256 (story 33).
- The architecture test that already forbids `document_versions` writes outside `core/documents` (version-replacement.md) extends to forbid `soft_deleted_at` writes outside `core/documents`, locking story 36's sole-writer invariant.
