# Single-VM Docker Compose topology, built on the host

## Status

Accepted

## Decision

BUSCASAM runs as a single Docker Compose stack on one UNSAM-provisioned VM, in dev and prod. Two Dockerfiles are owned in-repo (`backend/Dockerfile`, `frontend/Dockerfile`); all third-party runtime images are pinned by digest. Reverse proxy is **nginx**. Images are built on the VM from an explicit git commit/tag via `scripts/deploy.sh`. Persistent state is under `/var/lib/buscasam/` as bind mounts. Secrets live in one `.env` (mode 0600). TLS uses `TLS_MODE=upstream|self`. TEI model is pre-staged offline. Daily paired recovery points run through the backup service. Two distinct worker services run ADR-0008 queues. Centralized observability is post-MVP.

## Locked

1. Runtime: one Docker Compose stack, dev and prod. `compose.yaml` (dev), `compose.prod.yaml` (prod overrides - build mode, no host-port exposure on `db`, prod nginx config, `certbot` conditionally enabled). Both files describe eight steady-state services: `db`, `tei`, `api`, `worker_default`, `worker_ocr`, `frontend`, `nginx`, `backup`. `migrate` is invoked only via `docker compose run --rm migrate`; `certbot` is optional only in `TLS_MODE=self`.

2. Two Dockerfiles owned in-repo.

   - `backend/Dockerfile` - Python image. Deps include `pdfminer.six`, `ocrmypdf`, `python-docx`, `odfpy`, `yake`, `procrastinate`, `fastapi`, `uvicorn`, `sqlalchemy[asyncio]`, `alembic`, `authlib`, `httpx`, plus OS packages `tesseract-ocr`, `tesseract-ocr-spa`, `tesseract-ocr-eng`, `libmagic1`, `poppler-utils`, `postgresql-client`, and `rsync`. Four containers use this image:
     - `api`: `uvicorn buscasam.api.main:app --host 0.0.0.0 --port 8000 --workers 1`
     - `worker_default`: `procrastinate --app=buscasam.core.jobs.app worker --queues=default --concurrency=8`
     - `worker_ocr`: `procrastinate --app=buscasam.core.jobs.app worker --queues=ocr --concurrency=1`
     - `backup`: `scripts/backup_loop.sh`
   - `frontend/Dockerfile` — Node image (LTS pinned via `.nvmrc`). Multi-stage build producing `output: 'standalone'`. Entrypoint: `node server.js`.

   All external runtime images are pinned by digest: `pgvector/pgvector:pg16@sha256:...`, `ghcr.io/huggingface/text-embeddings-inference:cpu-...@sha256:...`, `nginx:1.27-alpine@sha256:...`, and optional `certbot/certbot@sha256:...`.

3. Reverse proxy: nginx.

   - `:80` always listening. In `TLS_MODE=upstream`, serves the app directly and trusts `X-Forwarded-Proto` / `X-Forwarded-For` from a single configured upstream CIDR. In `TLS_MODE=self`, returns 301 to `:443`.
   - `:443` only listening in `TLS_MODE=self`. Mounts `/etc/letsencrypt/` from a `certbot` sidecar.
   - Two upstreams: `api:8000` (for `location /api/`) and `frontend:3000` (everything else). The API proxy preserves the `/api/` prefix (`proxy_pass http://api:8000;`, without a trailing slash).
   - `location /_blobs/ { internal; alias /var/lib/buscasam/blobs/; sendfile on; tcp_nopush on; }` — verbatim from ADR-0006 §9. `blobs/` mount shared read-only with nginx.
   - `client_max_body_size 55m`; main and attachments are uploaded as separate requests under ADR-0006.

4. Service layout (steady-state graph):

   | Service | Image | Entrypoint | Persistent mounts | Restart |
   |---|---|---|---|---|
   | `db` | `pgvector/pgvector:pg16` | postgres default | `/var/lib/buscasam/postgres → PGDATA` | `unless-stopped` |
   | `tei` | TEI CPU pinned | `text-embeddings-router --model-id … --revision … --port 80` | `/var/lib/buscasam/tei-cache → /data` | `unless-stopped` |
   | `api` | `backend` | `uvicorn ... --workers 1` | `blobs` (rw) | `unless-stopped` |
   | `worker_default` | `backend` | `procrastinate worker --queues=default --concurrency=8` | `blobs` (rw) | `unless-stopped` |
   | `worker_ocr` | `backend` | `procrastinate worker --queues=ocr --concurrency=1` | `blobs` (rw) | `unless-stopped` |
   | `frontend` | `frontend` | `node server.js` | — | `unless-stopped` |
   | `nginx` | `nginx:1.27-alpine` | nginx default | `blobs` (ro), `/etc/nginx/conf.d` (config), `/etc/letsencrypt` (in `self`) | `unless-stopped` |
   | `backup` | `backend` | `scripts/backup_loop.sh` | `blobs` (ro), `/backup/buscasam` (rw) | `unless-stopped` |
   | `certbot` (`self` only) | `certbot/certbot` | `certonly --webroot --renew-by-default` cron | `/etc/letsencrypt` (rw), `/var/www/certbot` (rw) | `unless-stopped` |
   | `migrate` (`run --rm`) | `backend` | `bash -c 'alembic upgrade head && procrastinate schema --apply'` | — | `"no"` |

5. Healthchecks and `depends_on`.

   - `db`: `pg_isready -U buscasam -d buscasam`, 5 s interval, 5 retries.
   - `tei`: `curl -fsS http://localhost/health`, 10 s.
   - `api`: `curl -fsS http://localhost:8000/health` (process-liveness only, no DB ping).
   - `frontend`: `curl -fsS http://localhost:3000/`.
   - `nginx`, `worker_default`, `worker_ocr`, `backup`: no healthcheck.
   - `depends_on`:
     - `api`, `worker_default`, `worker_ocr`, `backup` -> `db (service_healthy)` only. TEI outage must not stop lexical search, queue monitoring, or maintenance.
     - `nginx` → `api (service_started)`, `frontend (service_started)`.
     - `frontend` → no dep on `api`.
     - `migrate` → `db (service_healthy)`.

6. Port exposure.

   - **Prod:** `nginx` binds `0.0.0.0:80` and `0.0.0.0:443`. No other service binds a host port.
   - **Dev:** additionally binds `db` to `127.0.0.1:5432` for host-side `psql` and ad-hoc Alembic invocations.

7. Persistent state — bind mounts under `/var/lib/buscasam/`. Owned by host user `buscasam:buscasam` (uid/gid via build args).

   ```
   /var/lib/buscasam/
   ├── postgres/        ← db PGDATA
   ├── blobs/           ← ADR-0006 §1
   │   ├── ab/cd/…      ← sharded sha256
   │   └── .tmp/        <- in-flight uploads on the same mount for atomic rename
   └── tei-cache/       <- pre-staged HF model
   /backup/buscasam/    <- bind to whatever UNSAM provides; see section 11
   └── recovery/<ts>/   <- paired `db.dump` and hard-linked `blobs/` snapshot, 14-day rotation
   ```

   No Docker named volumes.

8. Configuration: single `.env` on the VM. `compose.prod.yaml` loads `./.env` (mode 0600, gitignored) via `env_file:` per service, with per-service `environment:` allowlist. Repo ships `.env.example`. CI runs `python -m buscasam.config check-example` which loads the `Settings` schema and asserts every field appears in `.env.example`.

   - Secrets: `POSTGRES_PASSWORD`, `DATABASE_URL`, `SESSION_SECRET_KEY` (ADR-0005), `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `SMTP_USERNAME`, `SMTP_PASSWORD`.
   - Non-secret: `POSTGRES_USER`, `POSTGRES_DB`, `BUSCASAM_BASE_URL`, `BUSCASAM_INTERNAL_API_URL=http://api:8000/api` (frontend server only), `TEI_BASE_URL=http://tei`, `BLOB_ROOT=/var/lib/buscasam/blobs`, `TLS_MODE`, `TRUSTED_PROXY_CIDR`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM`, `EMBEDDING_MODEL_REVISION`, `EXTRACT_PIPELINE_VERSION`, `MIN_SEMANTIC_SIMILARITY`, `BACKUP_RETENTION_DAYS`.

   Rotation = edit `.env` and `docker compose up -d`.

9. TLS: two-mode nginx config, selected by `TLS_MODE`.

   - `TLS_MODE=upstream`: nginx listens `:80` only; trusts `X-Forwarded-Proto` / `X-Forwarded-For` from a single configured upstream CIDR (`TRUSTED_PROXY_CIDR` in `.env`). Auth cookies are always emitted `Secure`.
   - `TLS_MODE=self`: nginx listens `:80` (HTTP→HTTPS 301 + `.well-known/acme-challenge/`) and `:443` (full TLS); `certbot` sidecar runs `certonly --webroot --renew-by-default` on a 12-hour loop; nginx reload via shared `/etc/letsencrypt/` + a daily forced reload.
   - Both modes ship in the image; the active one is selected at container start by an entrypoint script that templates `nginx.conf` from `nginx.conf.template`.

10. TEI model pre-staging. First-time setup (`scripts/prestage_model.sh`, committed): from a workstation with `huggingface.co` reachability, download the pinned revision SHA, tar, scp to the VM, extract to `/var/lib/buscasam/tei-cache/`. TEI starts with `HF_HUB_OFFLINE=1` and explicit `--revision`. If cache is missing or revision-mismatched, the container exits non-zero. Tokenizer file vendored in the repo; startup assertion in `core/embed.py` refuses on mismatch. Model bump = re-run pre-staging script before deploy.

11. Backup execution: `backup` uses the backend image plus `postgresql-client` and `rsync`. Daily `scripts/backup_loop.sh` calls a small Python entrypoint that holds the same Postgres advisory lock used by GC while it:
    - creates `/backup/buscasam/recovery/<ts>/db.dump` using `pg_dump -Fc`;
    - creates `/backup/buscasam/recovery/<ts>/blobs/` using `rsync --link-dest` from the prior successful snapshot;
    - writes a completion marker only after both succeed, then rotates completed recovery points older than `BACKUP_RETENTION_DAYS=14`.

    Content-addressed blobs are immutable; writes concurrent with a dump may add harmless unreferenced files. The GC lock prevents a dump from referencing a blob deleted before its paired snapshot. A restore drill from one completed recovery point is required before launch. Destination priority:
    1. UNSAM-provided off-host mount (real DR).
    2. Separate disk on the VM (same-VM redundancy).
    3. Same disk under `/var/backup/buscasam/` (no redundancy).

12. Deploy via `scripts/deploy.sh <commit-or-tag>`:

    ```bash
    set -euo pipefail
    cd /opt/buscasam
    test -n "${1:-}"
    git fetch --tags origin
    git checkout --detach "$1"
    docker compose -f compose.prod.yaml build
    docker compose -f compose.prod.yaml up -d db
    docker compose -f compose.prod.yaml run --rm migrate
    docker compose -f compose.prod.yaml up -d
    docker image prune -f
    ```

    A failed `migrate` exits non-zero before `up -d`, leaving prior containers serving against a possibly upgraded schema. Therefore every MVP migration must be backward compatible with the previous deployed image (expand/contract only); destructive cleanup is a separately approved later deploy. Rollback is `scripts/deploy.sh <previous-commit-or-tag>`. CI runs tests, migration compatibility checks, a Compose config/build smoke check, and OpenAPI codegen diff check.

13. Schema apply: `migrate` runs `alembic upgrade head && procrastinate schema --apply`. The first Alembic migration executes `CREATE EXTENSION IF NOT EXISTS vector;`, `CREATE EXTENSION IF NOT EXISTS unaccent;`, `CREATE EXTENSION IF NOT EXISTS ltree;`, and the `CREATE TEXT SEARCH CONFIGURATION es_unaccent …` from ADR-0001 §8. No other extensions.

14. Resource and launch gate. Compose starts with `mem_limit:` on `tei: 3g` and `worker_ocr: 2g`; `db` carries `oom_score_adj: -500`. Postgres tuning lives in a mounted `postgresql.conf`. Before accepting production traffic, run a fixture benchmark on the provisioned VM covering concurrent search plus one OCR job; record p95 search latency, lexical fallback rate, index duration, and peak memory. Adjust limits/timeouts or VM size until the agreed acceptance values are met.

15. Logging: capped `json-file` driver via YAML anchor in `compose.prod.yaml`:

    ```yaml
    x-logging: &default-logging
      driver: json-file
      options:
        max-size: "10m"
        max-file: "5"
    ```

    applied to every long-running service. App processes write structured JSON to stdout. No host-side log shipping at MVP; `docker compose logs <svc>` is the operator surface.

16. Rate limiting at nginx. Limits apply regardless of the presence of an unvalidated `sid` cookie:

    - `auth_zone` keyed on `$binary_remote_addr`, 10 req/min burst 20 — applied to `/api/auth/login` and `/api/auth/google/callback`.
    - `read_zone` keyed on `$binary_remote_addr`, 60 req/min burst 120 - applied to `/api/search`, `/api/docs/*`, and download routes for all clients. A later backend-aware limit may differentiate authenticated users.

17. GPU upgrade path. Change the `image:` digest of `tei` and add `deploy.resources.reservations.devices: [driver: nvidia, count: all, capabilities: [gpu]]` (plus host-side NVIDIA Container Toolkit). All other services unaffected. Reversible.

## Open dependencies on UNSAM IT

- **DNS A record** for `buscasam.unsam.edu.ar` (or chosen hostname) pointing at the VM.
- **TLS topology confirmation:** UNSAM terminates TLS upstream (`TLS_MODE=upstream`) or we own certs (`TLS_MODE=self` + outbound to Let's Encrypt + inbound on `:80` for HTTP-01).
- **Outbound HTTPS** from the VM to `pypi.org`, `registry.npmjs.org`, `ghcr.io`, `github.com` (build-time).
- **One-time outbound** to `huggingface.co` from any workstation that can scp to the VM (pre-staging §10).
- **Backup mount:** off-host storage if available; otherwise same-VM redundancy.
- **Root or sudo on the VM** for first-time host setup (creating `buscasam:buscasam`, installing Docker, creating `/var/lib/buscasam/` and `/backup/buscasam/`).
- **Google Cloud OAuth client** scoped to the UNSAM Workspace tenants.
