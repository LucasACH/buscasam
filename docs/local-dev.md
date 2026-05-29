# Local development

How to bring up the full BUSCASAM stack on your machine. Path-prefixed commands assume the repo root; `cd backend/` where indicated.

## Prereqs

- Docker (with Compose v2)
- [`uv`](https://docs.astral.sh/uv/) for the Python backend
- [`pnpm`](https://pnpm.io/) for the Next.js frontend
- A Google OAuth 2.0 Client ID (Web application) with:
  - Authorized JavaScript origin: `http://localhost:3000`
  - Authorized redirect URI: `http://localhost:3000/api/auth/google/callback`

Only `@unsam.edu.ar` and `@estudiantes.unsam.edu.ar` Google Workspace accounts will pass `hd` validation (`core/auth.py:52-56`).

## One-time setup

```bash
cd backend
cp .env.example .env
```

Edit `backend/.env` and paste your OAuth credentials:

```
BUSCASAM_OIDC_CLIENT_ID=<your-client-id>
BUSCASAM_OIDC_CLIENT_SECRET=<your-client-secret>
BUSCASAM_BLOB_ROOT=./var/blobs
BUSCASAM_EMBED_QUERY_TIMEOUT_S=5
BUSCASAM_SERVE_BLOBS_INLINE=1
BUSCASAM_METADATA_LLM_ENABLED=0
BUSCASAM_METADATA_LLM_URL=http://localhost:11434
BUSCASAM_METADATA_LLM_MODEL=llama3.2:3b
BUSCASAM_METADATA_LLM_TIMEOUT_S=60
```

`BUSCASAM_EMBED_QUERY_TIMEOUT_S=5` overrides the prod default of `0.5` so semantic search actually fires on Apple Silicon (TEI runs amd64-emulated and easily blows past 500 ms).

`BUSCASAM_SERVE_BLOBS_INLINE=1` makes download endpoints stream the blob from disk instead of emitting `X-Accel-Redirect` for nginx (which doesn't exist locally). Leave unset in prod.

Optional staged metadata cleanup uses a local Ollama-compatible model. Install Ollama, run `ollama pull llama3.2:3b`, keep `ollama serve` listening on `http://localhost:11434`, then set `BUSCASAM_METADATA_LLM_ENABLED=1`. The worker calls `/api/generate` with `BUSCASAM_METADATA_LLM_MODEL` and a hard `BUSCASAM_METADATA_LLM_TIMEOUT_S=60`; timeout, outage, invalid JSON, or invalid schema falls back to deterministic extraction + YAKE and indexing still completes.

## Bring up infra

From `backend/`:

```bash
docker compose --profile tei up -d
```

This starts:

- `buscasam-db` (Postgres 16 + pgvector) on `localhost:5432`
- `buscasam-tei` (HuggingFace TEI) on `localhost:8080`, serving `intfloat/multilingual-e5-large`

First boot of TEI downloads ~3 GB of model weights — give it ~5 min before expecting embeds to succeed. Check with:

```bash
docker inspect -f '{{.State.Health.Status}}' buscasam-tei
```

## Migrate the database

```bash
cd backend
uv run alembic upgrade head
```

This creates all schema tables **including** procrastinate's job queue tables (migration `0012`).

## Seed fixtures (areas + sample corpus)

```bash
cd backend
uv run python -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from buscasam.settings import settings
from buscasam.fixtures.seed import seed

async def main():
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        await seed(conn)
    await engine.dispose()

asyncio.run(main())
"
```

Populates `areas` (escuelas/carreras/materias for the dropdowns) and 15 sample documents with chunks/embeddings. Without this the área dropdown is empty.

## Start the services

Run each in its own terminal.

**Backend** (FastAPI + uvicorn, auto-reload):

```bash
cd backend
uv run uvicorn --factory buscasam.api.app:create_app --reload --host 127.0.0.1 --port 8000
```

**Worker** (Procrastinate; processes upload/indexing jobs):

```bash
cd backend
uv run procrastinate --app=buscasam.core.jobs.app worker
```

**Frontend** (Next.js):

```bash
cd frontend
pnpm install   # first time only
pnpm dev
```

Open http://localhost:3000.

## End-to-end smoke check

1. http://localhost:3000/login → Sign in with Google.
2. /mis-trabajos/nuevo → upload a PDF.
3. Backend writes the blob under `backend/var/blobs/` and enqueues an `index_document` job.
4. Worker calls TEI for each chunk; `document_versions.index_status` goes `pending → processing → indexed`.
5. http://localhost:3000/buscar → search returns the new doc.

## Attachments

The editor (`/mis-trabajos/[id]/editar`) exposes an `AttachmentsPanel` for sidecar files (datasets, slides, source). Backend routes:

- `POST /api/documents/{doc_id}/attachments` (multipart `file`)
- `DELETE /api/documents/{doc_id}/attachments/{att_id}`

Constraints (`api/documents.py:250-256`):

- ≤ 5 attachments per document → 409 `attachment_cap_exceeded`
- ≤ 20 MB each → 413
- Allowed extensions: `.csv .json .txt .py .ipynb .png .jpg .jpeg .gif .zip` → 415 otherwise

Attachments share the same content-addressed `blob_store` as the main file, so the same `BUSCASAM_BLOB_ROOT` and writability rules apply. Allowed pre- and post-publish.

Smoke check:

1. Open a draft from `/mis-trabajos`.
2. Add a `.csv` or `.zip` ≤ 20 MB via the attachments panel.
3. Backend writes the blob under `backend/var/blobs/`; the row appears in `document_attachments`.
4. Remove it; row is deleted (blob stays for the orphan sweep — content-addressed, may be shared).

## Resetting state

`docker compose down -v` on macOS sometimes leaves the Postgres volume intact (Docker Desktop quirk). To genuinely wipe the database:

```bash
PGPASSWORD=buscasam psql -h localhost -p 5432 -U buscasam -d postgres -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity \
   WHERE datname='buscasam' AND pid <> pg_backend_pid();"
PGPASSWORD=buscasam psql -h localhost -p 5432 -U buscasam -d postgres -c \
  "DROP DATABASE buscasam;"
PGPASSWORD=buscasam psql -h localhost -p 5432 -U buscasam -d postgres -c \
  "CREATE DATABASE buscasam OWNER buscasam;"
```

Then re-run migrations and seed. Wipe blobs separately:

```bash
rm -rf backend/var/blobs
```

## Troubleshooting

- **"No se pudo subir el archivo"**: `backend/var/blobs/` not writable, or `BUSCASAM_BLOB_ROOT` unset. Check `backend/.env` is loaded (restart uvicorn after editing).
- **Upload sticks on "Procesando…"**: worker not running, or TEI not healthy. Tail the worker output and run `curl http://localhost:8080/health`.
- **Indexing jobs fail with `EmbedUnavailable`**: TEI cold or model still downloading. `docker logs buscasam-tei` and wait for `Ready`.
- **Search returns 0 results for slight typos**: `BUSCASAM_EMBED_QUERY_TIMEOUT_S` too low → silent lexical fallback. Look for `"lexical_fallback": true` in the `/api/search` response.
- **Login bounces to `/login?error=not_unsam`**: account isn't on a UNSAM Workspace domain (`hd` claim missing or not in `ROLE_BY_HD`).
- **Failed Procrastinate job won't retry**: `UPDATE procrastinate_jobs SET status='todo', attempts=0 WHERE id=<n>` and the worker picks it back up.
- **Attachment upload returns 415**: extension not in the allowlist (see Attachments). 413 → over 20 MB. 409 with `attachment_cap_exceeded` → doc already has 5 attachments.
