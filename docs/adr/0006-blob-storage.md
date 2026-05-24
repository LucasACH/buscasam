# Filesystem blob store, content-addressed, served via `X-Accel-Redirect`

## Status

Accepted

## Decision

Original document files (PDF/DOCX/ODT main artifacts and complementary attachments) are stored on a local filesystem mount at `/var/lib/buscasam/blobs/`, addressed by sha256 with a two-level shard. All filesystem IO lives behind `core/blob_store.py`. Versioning uses `documents` plus append-only `document_versions`; chunks are version-scoped and attachments document-scoped. Author deletion retains data for 180 days; moderation hiding is separate. Downloads use FastAPI access check then `X-Accel-Redirect`. Upload caps: main 50 MB, attachments 20 MB each, five maximum.

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

   Architecture tests require application blob reads/writes/deletes to use this module. Migrations, container scripts, and tests are excluded.
4. Atomic write protocol. Uploads stream into `/var/lib/buscasam/blobs/.tmp/<uuid4>.partial`, hashing as bytes arrive. On stream end: `fsync` the temp file, `os.rename` into the final sharded path. If the final path already exists (dedup hit), unlink the temp and return the existing path. Intermediate directories `os.makedirs(..., exist_ok=True)` ahead of rename. Startup hook in `blob_store` sweeps `/blobs/.tmp/` older than 24 hours.
5. Versioning data model:

   ```
   documents (
     id              bigserial primary key,
     title           text not null,
     area_path       ltree not null,                     -- ADR-0001 §7
     visibility      text not null,                       -- 'publico' | 'interno' | 'privado'
     publication_status text not null default 'draft',    -- ADR-0010 lifecycle
     soft_deleted_at timestamptz,                         -- author deletion
     moderation_hidden_at timestamptz,                    -- moderation hide, not purge trigger
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

   `document_versions` is append-only except for processing status/provenance and the `is_current` flag flip. No circular FK; `documents` does not carry a `current_version_id` pointer.
6. Chunks are version-scoped. The `chunks` table (ADR-0001) carries `version_id bigint not null references document_versions(id)` and a denormalized `is_current boolean`. Worker-created replacement chunks remain `is_current = false`. Only the author's publish transaction after successful indexing flips:

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

   Attachments inherit access and lifecycle from the document. The five-attachment cap is enforced transactionally. Main-file upload and each attachment upload are separate HTTP requests so proxy body limits match per-file limits.
8. Access on download. Endpoints flow through `core/document_access.py`:

   ```
   GET /api/docs/{id}/download                  → main file, current published version
   GET /api/docs/{id}/versions/{n}/download     → main file, specific version (owner/accepted authors only)
   GET /api/docs/{id}/attachments/{att_id}      → attachment
   ```

   Current-file and attachment handlers use ADR-0010 normal readable access. Historical versions use its author-management access. Moderation download is a separate docente-only endpoint tied to a report. Denial returns 404, not 403.
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

   `internal;` means clients can never request `/_blobs/...` directly. Integration/E2E runs nginx through Compose; unit tests may validate the access/header response without nginx.
10. Upload validation at the FastAPI boundary:
    - Size caps: main ≤ 50 MB; each attachment ≤ 20 MB; ≤ 5 attachments per document. Enforced on streamed byte count via `max_bytes`.
    - MIME sniff on main file (strict): `libmagic` reads first 2 KB; must be `application/pdf`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document`, or `application/vnd.oasis.opendocument.text`. Mismatch → 415.
    - Attachments: extension allowlist `.csv .json .txt .py .ipynb .png .jpg .jpeg .gif .zip` and similar. No content sniffing.
    - No malware scanning at MVP.
11. Author-delete retention. `documents.soft_deleted_at` triggers purge only after 180 days. ADR-0010 access excludes deleted and moderation-hidden documents. Hidden-only documents are retained until unhidden or separately author-deleted.
12. GC and orphan blob sweep - two daily jobs registered through ADR-0008 periodic defers:
    - Retention purge: `DELETE FROM documents WHERE soft_deleted_at < NOW() - INTERVAL '180 days'`. `ON DELETE CASCADE` collects versions, attachments, chunks, reports, and moderation actions. Idempotent.
    - Orphan blob sweep: scan filesystem for sha256s not referenced by any `document_versions.sha256` or `document_attachments.sha256` row; delete via `blob_store.delete`. Skip blobs whose final-path mtime is younger than 24 hours (configurable grace).
13. Backup and restore use ADR-0009 timestamped database-plus-blob recovery points. GC and backup coordinate so a retained database dump never points to a missing blob snapshot.
