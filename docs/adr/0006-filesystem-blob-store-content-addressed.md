# Filesystem blob store, content-addressed, served via `X-Accel-Redirect`

## Status

Accepted

## Decision

Original document files (PDF/DOCX/ODT main artifacts and complementary attachments — CSV, code, images) are stored on a single local filesystem mount at `/var/lib/buscasam/blobs/`, addressed by sha256 with a two-level directory shard (`/blobs/ab/cd/abcd…ef`). All filesystem IO lives behind one `core/blob_store.py` module, enforced by a CI grep that bans `pathlib`, `aiofiles`, `os.rename`, `os.unlink`, and `open(` from appearing elsewhere — same shape as ADR-0001 §9, ADR-0002 §3, ADR-0003 §3, and ADR-0005 §3. Versioning is modeled as `documents` plus an immutable, append-only `document_versions` table with a partial unique index `WHERE is_current`; chunks (ADR-0001 §3) are version-scoped via FK to `document_versions.id`. Attachments are document-scoped (`document_attachments`), not version-scoped — replacing the main file bumps the version, attaching a dataset does not. Soft-delete retention is 180 days from `documents.soft_deleted_at`, with no author-initiated early purge; a daily queue job (ADR-0003 §4, ADR-0008) deletes expired rows and sweeps orphan blobs with a 24-hour grace window to avoid racing in-flight uploads. Downloads flow `FastAPI → visibility check via the search_query chokepoint → 200 + X-Accel-Redirect: /_blobs/<sharded-sha256>` and nginx serves the bytes from the `internal;` location — auth in app, IO in the proxy. Upload validation caps main files at 50 MB and attachments at 20 MB × 5, with libmagic sniffing on the main artifact and an extension allowlist on attachments; no malware scanner runs at MVP. Backup is `rsync --delete` to a single mirrored directory, on the same cron and same retention posture as ADR-0001's `pg_dump`.

## Context

SPEC §Edición requires "reemplazo de archivo crea una nueva versión" with the search using the latest version and history visible; §Eliminación requires soft-delete with audit/recovery retention; §Corpus accepts PDF/DOCX/ODT for indexing and CSV/código/imágenes as complementary attachments. ADR-0001 fixes a single-VM, single-Postgres-instance shape with daily `pg_dump` and rules out adding stateful services that don't carry their own weight. ADR-0003 fixes FastAPI + worker on shared `core/` code, with the queue as the only seam between processes and an "in-request work only for pure DB writes" posture. ADR-0005 fixes the visibility predicate's input contract — every request carries a `UserCtx`, and the predicate from ADR-0001 §9 is the sole gatekeeper. The decision to be made: where the bytes live, how they're addressed, who serves them on download, and how versioning / retention / backup all interact without compromising the existing chokepoint discipline. The corpus is small (≤50k docs at MVP, ≤200k at 5-year horizon), academic PDFs sit comfortably under 20 MB, the team is small, and UNSAM on-prem hardware is the deployment target.

## Considered options

- **Postgres `bytea` / large objects.** Rejected: ADR-0001's "one system, daily `pg_dump`" story collapses once the corpus carries GBs of binary content. Backup time, dump size, and search-DB IO budget all get coupled to upload/download traffic; the chunks/embeddings hot path competes with file IO for the same buffer cache.
- **S3-compatible (MinIO local, S3 prod).** Rejected at this scope: introduces a second stateful service with its own deployment, backup story, and access model. The features that would justify it — presigned-URL downloads scaling past one host, multi-region replication, deep object lifecycle policies — aren't in scope at single-VM MVP. Revisit if UNSAM provisions object storage, if downloads ever need to scale off-host, or if the blob mount outgrows what a single VM can hold.
- **ID-addressed layout (`/docs/{doc_id}/v{n}/main.pdf`).** Rejected: human-readable but couples on-disk identity to the document/version graph, makes dedup impossible, and turns versioning into a directory-mutation problem instead of an append-only one. Content addressing decouples blobs from rows: a version is "a row that points at a hash", not "a directory layout to maintain."
- **`Storage` Protocol with a `FilesystemStorage` implementation for future S3 swap.** Rejected: CLAUDE.md forbids speculative abstraction, and an interface designed against POSIX semantics (atomic rename, internal paths for `X-Accel-Redirect`) tends not to survive contact with S3's actual surface (presigned URLs, eventual consistency, no rename). The migration cost is in `blob_store.py` plus the nginx config either way; front-loading an interface adds maintenance without changing the migration scope. The chokepoint pattern is the real abstraction.
- **Stream downloads through FastAPI (`FileResponse`).** Rejected: a slow client downloading a 30 MB PDF pins a Uvicorn worker for the duration; nginx is built for that workload and handles `Range:`, `ETag`, and `Content-Disposition` natively. The auth gate still lives in FastAPI; only the bytes are handed off.
- **Direct nginx serving of `público` content (skip FastAPI for guest downloads).** Rejected: creates a second code path with different audit/counter/rate-limit semantics, for marginal latency benefit. All downloads go through the visibility chokepoint, no exceptions.
- **Author-requested early purge with docente approval.** Rejected at MVP scope: adds UI, a new moderation queue artifact, and bypasses the simpler "wait for the timer" model. Soft-delete already gives authors the unilateral hide action; physical destruction can wait 180 days.
- **Version-scoped attachments.** Rejected: SPEC's versioning language is about the indexed artifact ("reemplazo de archivo"). Forcing attachments to re-attach on every main-file replacement clutters the history view with main-content-identical versions and confuses author UX.
- **ClamAV / VirusTotal at upload time.** Rejected at MVP: the upload surface is closed to `hd`-gated UNSAM accounts (ADR-0005 §2), downloads are `Content-Disposition: attachment` so browsers don't auto-execute, and moderation (SPEC §Moderación) handles the "this file is bad" case reactively. ClamAV adds an always-on sidecar for an unmeasured risk; VirusTotal leaks file hashes to a third party and is quota-limited. Revisit on first real incident.
- **`restic` / `borg` snapshots from day one.** Rejected: ADR-0001's blob-tier analogue is `pg_dump`, not `pgBackRest`. Match the sophistication tier. Content-addressed immutable blobs make `rsync --delete` essentially a metadata diff; restore is trivial and tool-agnostic. Revisit when off-host backup storage is provisioned.

## Architecture decisions locked by this ADR

1. **Storage backend.** Local filesystem mount at `/var/lib/buscasam/blobs/`, owned by the buscasam service user, group-readable by nginx. Configured via `pydantic-settings` (ADR-0003 §7) so dev environments can point at a tmp directory. No second stateful service is introduced; the mount is part of the single-VM topology (ADR-0009 territory).
2. **Addressing.** Content-addressed by sha256 of the file bytes. Two-level directory shard using the first two and next two hex characters of the hash: `/blobs/ab/cd/abcd1234…ef`. No file extension on the on-disk filename; `Content-Type` and `Content-Disposition` are set from the metadata row at download time. Sharding caps any one directory at ≤256 children per level (≤65k blobs per leaf at 16-char balance), well within ext4/xfs comfort zones at the 5-year corpus horizon.
3. **`blob_store` chokepoint.** One module — `core/blob_store.py` — owns all filesystem IO. Public surface:

   ```python
   async def put_stream(stream, *, max_bytes: int) -> BlobPutResult  # returns sha256, bytes, sniffed_mime
   async def open_for_send(sha256: str) -> AsyncIterator[bytes]      # for tests + dev fallback
   def internal_path(sha256: str) -> str                              # for X-Accel-Redirect header
   async def exists(sha256: str) -> bool
   async def delete(sha256: str) -> None                              # GC use only
   ```

   A CI grep blocks `pathlib`, `aiofiles`, `os.rename`, `os.unlink`, `os.fsync`, and bare `open(` from appearing outside `core/blob_store.py` (excluding tests, Alembic migrations, vendored code). Same shape as ADR-0001 §9, ADR-0002 §3, ADR-0003 §3, ADR-0005 §3.
4. **Atomic write protocol.** Uploads stream into `/var/lib/buscasam/blobs/.tmp/<uuid4>.partial`, hashing as bytes arrive. On stream end: `fsync` the temp file, then `os.rename` into the final sharded path. Rename is atomic on POSIX; if the final path already exists (dedup hit, identical content), the temp file is unlinked and the existing path is returned. The intermediate directories (`/blobs/ab/cd/`) are `os.makedirs(..., exist_ok=True)` ahead of the rename. Partial files survive crashes; a startup hook in `blob_store` sweeps `/blobs/.tmp/` older than 24 hours.
5. **Versioning data model.**

   ```
   documents (
     id              bigserial primary key,
     title           text not null,
     area_path       ltree not null,                     -- ADR-0001 §7
     visibility      text not null,                       -- 'publico' | 'interno' | 'privado'
     soft_deleted_at timestamptz,                         -- null = live; non-null = soft-deleted
     created_at      timestamptz not null default now(),
     ...
   )

   document_versions (
     id                bigserial primary key,
     doc_id            bigint not null references documents(id) on delete cascade,
     version_no        int not null,                      -- 1, 2, 3, …
     sha256            bytea not null,                    -- 32 bytes, references the on-disk blob
     original_filename text not null,                     -- for Content-Disposition
     bytes             bigint not null,
     mime              text not null,                     -- 'application/pdf' | … (sniffed, not client-declared)
     uploaded_at       timestamptz not null default now(),
     uploaded_by       bigint not null references users(id),
     is_current        boolean not null default false
   )
   CREATE UNIQUE INDEX ON document_versions (doc_id) WHERE is_current;
   CREATE UNIQUE INDEX ON document_versions (doc_id, version_no);
   ```

   `document_versions` is append-only — rows are never updated except for the `is_current` flag flip. No circular FK; `documents` does not carry a `current_version_id` pointer.
6. **Chunks are version-scoped.** The `chunks` table from ADR-0001 §3 carries `version_id bigint not null references document_versions(id)` and an `is_current boolean` denormalized from the parent version. Search filters on `WHERE is_current` via a partial index, keeping the hot-path graph small without joining `document_versions`. Replacement = new version row (`is_current = false`) + worker generates new chunks → atomic flip in one transaction: `UPDATE chunks SET is_current = false WHERE version_id = :old; UPDATE chunks SET is_current = true WHERE version_id = :new; UPDATE document_versions SET is_current = false WHERE id = :old; UPDATE document_versions SET is_current = true WHERE id = :new;` Until the flip, search keeps serving the previous version.
7. **Attachments are document-scoped, independent.**

   ```
   document_attachments (
     id                bigserial primary key,
     doc_id            bigint not null references documents(id) on delete cascade,
     sha256            bytea not null,
     original_filename text not null,
     bytes             bigint not null,
     mime              text,                              -- not load-bearing; allowlist by extension
     uploaded_at       timestamptz not null default now(),
     uploaded_by       bigint not null references users(id)
   )
   CREATE INDEX ON document_attachments (doc_id);
   ```

   Attaching or removing a dataset never bumps the main-file version. Attachments inherit the document's `visibility` and `soft_deleted_at`; no independent visibility per attachment. Per-document cap of 5 attachments enforced at the API boundary.
8. **Visibility on download.** Both download endpoints flow through the search_query chokepoint:

   ```
   GET /api/docs/{id}/download                  → main file, latest version
   GET /api/docs/{id}/versions/{n}/download     → main file, specific version (authors/docentes only)
   GET /api/docs/{id}/attachments/{att_id}      → attachment
   ```

   Each handler calls `search_query.can_access(user_ctx, doc_id)`, which composes the ADR-0001 §9 visibility predicate. Historical version downloads add an extra check: `current_user.user_id in document.authors OR current_user.role == 'docente'`; everyone else gets the current version only. Denial returns 404, not 403, to avoid leaking existence of `privado`/`interno` documents to unauthenticated requesters.
9. **Download serving via `X-Accel-Redirect`.** On a successful visibility check, the handler returns 200 with no body and these headers:

   ```
   X-Accel-Redirect: /_blobs/ab/cd/abcd1234…ef
   Content-Type: <mime from row>
   Content-Disposition: attachment; filename*=UTF-8''<urlencoded original_filename>
   ```

   nginx config:

   ```
   location /_blobs/ {
       internal;
       alias /var/lib/buscasam/blobs/;
       sendfile on;
       tcp_nopush on;
   }
   ```

   The `internal;` directive means clients can never request `/_blobs/...` directly — only an upstream-response redirect can reach it. Range requests, ETags, and conditional GETs are handled by nginx without further app involvement. Dev environments run nginx via `docker-compose` to match prod's auth-then-redirect flow; no Python-side streaming fallback (one path, one mental model).
10. **Upload validation.** Enforced at the FastAPI boundary, before `blob_store.put_stream` returns:
    - **Size caps.** Main file ≤ 50 MB; each attachment ≤ 20 MB; ≤ 5 attachments per document. Enforced on streamed byte count (the `max_bytes` argument to `put_stream`), not client `Content-Length`. Violation aborts the stream and unlinks the partial.
    - **MIME sniffing on main file (strict).** `libmagic` via `python-magic` reads the first 2 KB and must return `application/pdf`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document`, or `application/vnd.oasis.opendocument.text`. Mismatch → 415.
    - **Attachments: extension allowlist (loose).** `.csv .json .txt .py .ipynb .png .jpg .jpeg .gif .zip` and similar. No content sniffing; attachments are never parsed downstream, so a wrong content-type only affects browser preview.
    - **No malware scanning** at MVP. Flagged for revisit on first incident or if `público`-tier accidental hosting becomes a concern.
11. **Soft-delete retention.** `documents.soft_deleted_at` is a `timestamptz` (replaces a boolean — the timestamp doubles as the GC trigger). The visibility predicate (ADR-0001 §9) excludes any row with `soft_deleted_at IS NOT NULL` from search and download. No early purge path — authors can't physically destroy content, only docentes via the moderation flow (and even there, "hide" is the soft-delete action). Retention window: 180 days.
12. **GC and orphan blob sweep.** Two passes, both enqueued daily by ADR-0008's scheduler:
    - **Retention purge.** `DELETE FROM documents WHERE soft_deleted_at < NOW() - INTERVAL '180 days'`. `ON DELETE CASCADE` collects `document_versions`, `document_attachments`, `chunks`, comments, favourites, reports. Idempotent; safe to re-run.
    - **Orphan blob sweep.** Scans the filesystem for sha256s not referenced by any `document_versions.sha256` or `document_attachments.sha256` row, deletes them via `blob_store.delete`. Includes a 24-hour grace window — a blob whose final-path mtime is younger than 24 hours is skipped, even if currently unreferenced, to avoid racing an in-flight upload whose metadata row hasn't been committed yet. The grace window is configurable; 24 h is the default.
13. **Backup.** Daily cron, paired with `pg_dump` from ADR-0001 §1:

    ```
    rsync -a --delete /var/lib/buscasam/blobs/ /backup/buscasam/blobs/
    ```

    Single mirrored copy, no rotation. Content-addressed immutable blobs make `rsync --delete` cheap (metadata diff + new-file copy); the `--delete` flag is correct because GC has authority — purged means purged, including in the backup. The `/backup/` mount is whatever UNSAM provides; if it's another disk on the same VM, this is same-VM redundancy, matching the `pg_dump` posture (not real DR). Revisit when off-host storage exists.

## Consequences

- **Two backup artifacts must stay in sync.** `pg_dump` captures the metadata; `rsync` captures the blobs. A `pg_dump` from 03:00 and an `rsync` from 03:05 are consistent if no writes happened in between, which is approximately always at MVP scale, but a corner case exists where a version row points at a blob that doesn't yet exist in the backup mirror. Mitigation: the orphan sweep on restore is idempotent, and a missing-blob download returns 500 (not silent corruption). Acceptable trade. If RPO ever tightens, the right answer is `restic` snapshots of both at a coordinated instant.
- **Content addressing is permanent vocabulary.** Every blob is forever known by its sha256. If a stronger hash is ever needed (sha256 is fine for the foreseeable future), migration means rewriting both the on-disk layout and every row in `document_versions.sha256` / `document_attachments.sha256` in one coordinated job. Cost is a new ADR superseding this one — not a refactor.
- **The `X-Accel-Redirect` coupling makes dev environments slightly heavier.** A bare `uvicorn` run with no nginx in front can't exercise the download path end-to-end; `docker-compose` is required. Acceptable: the same is true for ADR-0004's SSR-cookie-forwarding path. One topology, one mental model.
- **Worker contention on downloads is offloaded.** Uvicorn workers handle visibility checks (fast SQL) and return immediately; nginx holds the connection for the bytes. Sizing the worker count is, as in ADR-0003, a memory question, not a download-throughput question.
- **Chunks-are-version-scoped makes the `is_current` flip a transaction with N row updates.** At ≤20 chunks per doc this is trivial; at edge-case 200-chunk documents (large theses) the transaction is still well under 100ms. Search read traffic is uninterrupted because the flip is one tx — readers see either the old version's chunks or the new version's, never a mix.
- **Old-version downloads leak no bytes to non-authors.** The 404-vs-403 rule (§8) is load-bearing: an invitado probing `/api/docs/42/versions/1/download` for a `privado` document gets the same 404 as for a non-existent id. Same gravity as ADR-0001's visibility predicate; same risk if a feature handler short-circuits it.
- **180 days is anchored to academic cycles, not to a regulatory floor.** If UNSAM ever attaches a data-retention regulation to the platform, this number gets re-justified or replaced. Flagged.
- **No malware scan = institutional trust posture.** ADR-0005's `hd`-gated upload surface plus SPEC §Moderación's reactive flow are the controls. The day a malicious file reaches a user is the day this ADR is re-opened, not a hypothetical we pre-build for.
- **Dedup is silent and per-blob.** Two students uploading the same paper share a blob on disk; their `document_versions` rows are independent, their visibility is independent, their soft-delete timing is independent. The blob sticks around until all referencing rows are purged. No surprise; just a consequence of content addressing worth naming.
- **Migration to S3 is a future ADR, not a present interface.** When/if it happens: rewrite `core/blob_store.py` (the chokepoint contains the entire surface), swap `X-Accel-Redirect` for `307` to a presigned URL, change the backup script. Feature code is untouched. The chokepoint earns its keep at that moment.
- **Four chokepoints, one pattern.** Search (introduced in ADR-0001 §9, formalised as `core/search_query.py` in ADR-0003 §3), embed (ADR-0002 §3), auth (ADR-0005 §3), and now blob IO (this ADR §3). Load-bearing-for-correctness logic — visibility predicates, model calls, role mapping, filesystem mutation — lives in one named module behind a CI grep. The cost is one extra CI rule per chokepoint; the benefit is that "where does X happen?" always has exactly one answer.
