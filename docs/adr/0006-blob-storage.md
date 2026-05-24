# Filesystem blob store, content-addressed, served via `X-Accel-Redirect`

## Status

Accepted

## Decision

Original document files (PDF/DOCX/ODT main artifacts and complementary attachments) stored on a local filesystem mount at `/var/lib/buscasam/blobs/`, addressed by sha256 with a two-level shard (`/blobs/ab/cd/abcd…ef`). All filesystem IO behind `core/blob_store.py`. Versioning: `documents` + immutable append-only `document_versions` with partial unique index `WHERE is_current`. Chunks version-scoped. Attachments document-scoped. Soft-delete retention 180 days. Downloads: FastAPI visibility check → 200 + `X-Accel-Redirect`. Upload caps: main 50 MB, attachments 20 MB × 5. Backup via `rsync --delete` paired with `pg_dump`.

## Locked

1. Storage backend: local filesystem mount at `/var/lib/buscasam/blobs/`, owned by the buscasam service user, group-readable by nginx. Configured via `pydantic-settings`.
2. Addressing: content-addressed by sha256 of file bytes. Two-level directory shard from the first two then next two hex characters: `/blobs/ab/cd/abcd1234…ef`. No file extension on the on-disk filename; `Content-Type` and `Content-Disposition` set from the metadata row at download time.
3. `blob_store` chokepoint at `core/blob_store.py`. Public surface:

   ```python
   async def put_stream(stream, *, max_bytes: int) -> BlobPutResult  # returns sha256, bytes, sniffed_mime
   async def open_for_send(sha256: str) -> AsyncIterator[bytes]
   def internal_path(sha256: str) -> str                              # for X-Accel-Redirect header
   async def exists(sha256: str) -> bool
   async def delete(sha256: str) -> None                              # GC use only
   ```

   CI grep blocks `pathlib`, `aiofiles`, `os.rename`, `os.unlink`, `os.fsync`, and bare `open(` outside `core/blob_store.py` (excluding tests, Alembic migrations, vendored code).
4. Atomic write protocol. Uploads stream into `/var/lib/buscasam/blobs/.tmp/<uuid4>.partial`, hashing as bytes arrive. On stream end: `fsync` the temp file, `os.rename` into the final sharded path. If the final path already exists (dedup hit), unlink the temp and return the existing path. Intermediate directories `os.makedirs(..., exist_ok=True)` ahead of rename. Startup hook in `blob_store` sweeps `/blobs/.tmp/` older than 24 hours.
5. Versioning data model:

   ```
   documents (
     id              bigserial primary key,
     title           text not null,
     area_path       ltree not null,                     -- ADR-0001 §7
     visibility      text not null,                       -- 'publico' | 'interno' | 'privado'
     soft_deleted_at timestamptz,                         -- null = live
     created_at      timestamptz not null default now(),
     ...
   )

   document_versions (
     id                bigserial primary key,
     doc_id            bigint not null references documents(id) on delete cascade,
     version_no        int not null,                      -- 1, 2, 3, …
     sha256            bytea not null,                    -- 32 bytes
     original_filename text not null,                     -- for Content-Disposition
     bytes             bigint not null,
     mime              text not null,                     -- sniffed, not client-declared
     uploaded_at       timestamptz not null default now(),
     uploaded_by       bigint not null references users(id),
     is_current        boolean not null default false
   )
   CREATE UNIQUE INDEX ON document_versions (doc_id) WHERE is_current;
   CREATE UNIQUE INDEX ON document_versions (doc_id, version_no);
   ```

   `document_versions` is append-only — rows are never updated except for the `is_current` flag flip. No circular FK; `documents` does not carry a `current_version_id` pointer.
6. Chunks are version-scoped. The `chunks` table (ADR-0001 §3) carries `version_id bigint not null references document_versions(id)` and a denormalized `is_current boolean`. Search filters on `WHERE is_current` via partial index. Replacement = new version row (`is_current = false`) + worker generates new chunks → atomic flip in one transaction:

   ```sql
   UPDATE chunks SET is_current = false WHERE version_id = :old;
   UPDATE chunks SET is_current = true  WHERE version_id = :new;
   UPDATE document_versions SET is_current = false WHERE id = :old;
   UPDATE document_versions SET is_current = true  WHERE id = :new;
   ```
7. Attachments are document-scoped, independent of versions:

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

   Attachments inherit `visibility` and `soft_deleted_at` from the document. Per-document cap of 5 attachments enforced at the API boundary.
8. Visibility on download. Both endpoints flow through the search_query chokepoint:

   ```
   GET /api/docs/{id}/download                  → main file, latest version
   GET /api/docs/{id}/versions/{n}/download     → main file, specific version (authors/docentes only)
   GET /api/docs/{id}/attachments/{att_id}      → attachment
   ```

   Each handler calls `search_query.can_access(user_ctx, doc_id)`. Historical version downloads add an extra check: `current_user.user_id in document.authors OR current_user.role == 'docente'`. Denial returns 404, not 403.
9. Download serving via `X-Accel-Redirect`. On a successful visibility check, the handler returns 200 with no body and these headers:

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

   `internal;` means clients can never request `/_blobs/...` directly. Dev environments run nginx via `docker-compose` to match prod; no Python-side streaming fallback.
10. Upload validation at the FastAPI boundary:
    - Size caps: main ≤ 50 MB; each attachment ≤ 20 MB; ≤ 5 attachments per document. Enforced on streamed byte count via `max_bytes`.
    - MIME sniff on main file (strict): `libmagic` reads first 2 KB; must be `application/pdf`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document`, or `application/vnd.oasis.opendocument.text`. Mismatch → 415.
    - Attachments: extension allowlist `.csv .json .txt .py .ipynb .png .jpg .jpeg .gif .zip` and similar. No content sniffing.
    - No malware scanning at MVP.
11. Soft-delete retention. `documents.soft_deleted_at timestamptz` (replaces a boolean — timestamp doubles as GC trigger). Visibility predicate (ADR-0001 §9) excludes any row with `soft_deleted_at IS NOT NULL`. No early purge. Retention: 180 days.
12. GC and orphan blob sweep — two daily jobs enqueued by ADR-0008's scheduler:
    - Retention purge: `DELETE FROM documents WHERE soft_deleted_at < NOW() - INTERVAL '180 days'`. `ON DELETE CASCADE` collects `document_versions`, `document_attachments`, `chunks`, comments, favourites, reports. Idempotent.
    - Orphan blob sweep: scan filesystem for sha256s not referenced by any `document_versions.sha256` or `document_attachments.sha256` row; delete via `blob_store.delete`. Skip blobs whose final-path mtime is younger than 24 hours (configurable grace).
13. Backup. Daily cron, paired with `pg_dump`:

    ```
    rsync -a --delete /var/lib/buscasam/blobs/ /backup/buscasam/blobs/
    ```

    Single mirrored copy, no rotation. `/backup/` mount per ADR-0009.
