# Replacement candidate lifecycle: at-most-one, discarded state, first_published_at

## Status

Accepted

## Decision

Replacement of a document's main file is modeled as a candidate version whose lifecycle is constrained by three new invariants on top of ADR-0010 §3 / ADR-0006 §5: at most one non-current, non-discarded candidate exists per document at any moment; an in-flight candidate can be terminated by an author-issued `discarded` transition that the worker honors before any write; the historic-version download surface is gated by a new `first_published_at` column rather than by `is_current` plus historical inference. The previously published current version remains the public-readable version through every state of any candidate (processing, failed, discarded, ready_to_publish).

## Locked

1. Candidate identity. For a given `doc_id`, "the candidate" is the row in `document_versions` with `is_current = false` and `index_status NOT IN ('discarded')`. ADR-0010 §3's state machine is extended:

   ```
   document_versions.index_status: pending -> processing -> indexed | failed | discarded
   ```

   `discarded` is a terminal state; `failed` and `indexed` may transition to `discarded`. `indexed -> discarded` only occurs when the candidate was not promoted to current (a published current version is by definition `indexed` and not discardable; descartar a current version is not a feature).

2. At-most-one candidate per document. A partial unique index enforces the invariant at the database boundary:

   ```sql
   CREATE UNIQUE INDEX document_versions_one_candidate
     ON document_versions (doc_id)
     WHERE is_current = false AND index_status <> 'discarded';
   ```

   Inserting a new candidate while another non-discarded candidate exists is a primary-key-like violation: the API contract forbids it, the schema enforces it, and the `core/documents.replace_main_version` chokepoint transitions any pre-existing candidate to `discarded` (inside the same transaction as the insert) so the partial index admits the new row.

3. First publication semantics. A new column tracks "this version was at some point the public current":

   ```sql
   ALTER TABLE document_versions
     ADD COLUMN first_published_at timestamptz;
   ```

   The publish transaction (ADR-0006 §6) sets `first_published_at = now()` on the candidate being promoted, only if it is currently `NULL`. A republish of a never-cleared row is not modeled — once set, the column is immutable. Backfill: existing `is_current = true` rows get `first_published_at = uploaded_at` (the migration's best-effort proxy; the corpus is small).

4. Historic-version download gate. `GET /api/docs/{id}/versions/{n}/download` (ADR-0006 §8) admits a version only if `first_published_at IS NOT NULL` AND the requester satisfies `manageable_where`. Failed candidates, discarded candidates, and in-flight ready candidates are not downloadable through this endpoint regardless of role. The Versiones panel rendered from `core/documents.get_detail` filters the `versions` list to the same predicate.

5. Worker contract. The `_begin_indexing` row lock (ADR-0008 §3 task body) extends its short-circuit:

   ```
   IF index_status = 'indexed' THEN return None (retry no-op).
   IF index_status = 'discarded' THEN return None (descartado, abort task).
   ELSE move to 'processing' and proceed.
   ```

   Every domain write the worker makes (`write_indexed_candidate`, `mark_failed`, `write_headline`) is gated by `WHERE index_status = 'processing'` (or in the headline case, `WHERE index_status = 'indexed' AND id = :version_id`) so a descartar transition between the lock release and the commit aborts the worker write atomically. No worker side effect can resurrect a discarded row.

6. Descartar contract. `core/documents.discard_candidate(session, user_ctx, doc_id)` (manageable-scoped per ADR-0010 §8):
   - Selects the candidate (per §1) `FOR UPDATE`. If none, raises `NoCandidateToDiscard` → 404.
   - Sets `index_status = 'discarded'`.
   - Deletes any `chunks` rows belonging to that `version_id`. Those rows always have `is_current = false` (only the publish transaction flips a candidate to current), so search visibility is unchanged.
   - Does not delete the `document_versions` row, does not delete the blob (orphan sweep collects the blob when no other version or attachment references its sha256, ADR-0006 §12).

7. Replacement upload contract. `core/documents.replace_main_version(session, user_ctx, doc_id, blob, *, original_filename)` (manageable):
   - Asserts a published current version exists; raises `NoPublishedVersion` → 409 otherwise (initial upload uses `/upload`, not `/replace`).
   - If a non-discarded candidate exists, calls `discard_candidate` semantics inline (same transaction).
   - Inserts a new `document_versions` row with `version_no = COALESCE(MAX(version_no), 0) + 1`, `index_status = 'pending'`, `is_current = false`, `first_published_at = NULL`.
   - Pre-fills `staged_abstract`, `staged_keywords`, `staged_fecha` from the document's currently published `documents.abstract`, `documents.keywords`, `documents.fecha` so polling clients see sensible values during the extraction window. The worker overwrites all three on indexing completion with the new file's `derive_metadata()` output (ADR-0007 §2); the worker contract is uniform across initial and replacement extraction.
   - Enqueues `index_document(version_id)` through the same transaction (ADR-0008 §1).

8. Edit-during-candidate. ADR-0010 §4's "metadata edits after publication persist immediately + enqueue headline reindex" remains the rule while a candidate exists. `update_draft_metadata` writes title/abstract to `documents` immediately (the published headline reindexes), and additionally writes them to the candidate's `staged_*` (the candidate's headline_fingerprint invalidates and `refresh_headline` enqueues for the candidate's version_id). Two reindexes can be in flight, one per version_id; ADR-0008 §3's per-version queueing locks (`headline:v{id}`) keep them independent.

9. Endpoints introduced:

   ```
   POST   /api/documents/{id}/replace        202 / 404 / 409 / 413 / 415   (manageable)
   DELETE /api/documents/{id}/candidate      204 / 404                     (manageable)
   ```

   `POST /upload` retains its initial-publication semantics (called before the first publish): inserting on a document that already has a published current version raises `AlreadyPublished` → 409. `POST /replace` is the inverse (callable only when a published current version exists). The router signals reuse the existing `core/blob_store.put_stream` + encrypted-PDF probe + `_ALLOWED_MIMES` gate.

10. Invariant under failure modes:
    - Replace upload fails synchronously (415, 413): no candidate row is created; the previously published version is unchanged.
    - Replace upload succeeds but `index_document` fails: the candidate transitions to `failed`; the published current version is unchanged; the author sees a `processing_failed` notification (ADR-0010 §3 notification kind) and a Candidata panel with a Descartar button. Re-issuing `/replace` while a `failed` candidate exists is admitted: the API discards the failed row inline (per §2's chokepoint behavior) and inserts a new candidate. The schema does not require an explicit DELETE first.
    - Worker is mid-flight when descartar fires: §5's gate aborts the write. The descartar transaction may commit before, during, or after the worker's extract IO; the SQL `WHERE` clauses in the worker writes are the source of truth.

11. Reads stay on `is_current`. The reader-facing predicates (ADR-0010 §6-§7, search, related, detail, current-version download, attachments, sitemap) continue to admit only `document_versions.is_current = true` rows. `first_published_at` is only consulted by the historic-version download endpoint and the Versiones panel projection. A reader path consulting `first_published_at` would be a bug.

12. Architecture tests:
    - `document_versions` writes outside `core/documents` are forbidden (architecture test extending the existing chokepoint rule).
    - Replacement insertion goes through `replace_main_version`; `attach_main_version` keeps its initial-publication contract and refuses on a document with a published current version. Both are exercised by integration tests.
    - The partial unique index from §2 is asserted by a schema test (matches `test_indices.py` precedent).
