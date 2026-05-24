# Single-VM Docker Compose topology, built on the host

## Status

Accepted

## Decision

BUSCASAM runs as a single Docker Compose stack on one UNSAM-provisioned VM, in dev and prod. Two Dockerfiles owned in-repo (`backend/Dockerfile`, `frontend/Dockerfile`); three external images pinned by digest (`pgvector/pgvector:pg16`, TEI CPU, nginx). Reverse proxy is **nginx**. Images built on the VM from `git pull` via `scripts/deploy.sh`. Persistent state under `/var/lib/buscasam/` as bind mounts. Secrets in a single `.env` (mode 0600). TLS via `TLS_MODE=upstream|self`. TEI model pre-staged offline. Daily `pg_dump` + `rsync` via backup sidecar. Two distinct worker services. Memory caps on `tei` and `worker_ocr`; Postgres `oom_score_adj: -500`. Observability deferred to ADR-0010.

## Locked

1. Runtime: one Docker Compose stack, dev and prod. `compose.yaml` (dev), `compose.prod.yaml` (prod overrides — build mode, no host-port exposure on `db`, prod nginx config, `certbot` conditionally enabled). Both files describe the same eight services: `db`, `tei`, `api`, `worker_default`, `worker_ocr`, `frontend`, `nginx`, `backup`. A ninth service `migrate` exists in both but is only invoked via `docker compose run --rm migrate`.

2. Two Dockerfiles owned in-repo.

   - `backend/Dockerfile` — Python image. Deps include `pdfminer.six`, `ocrmypdf`, `python-docx`, `odfpy`, `yake`, `procrastinate`, `fastapi`, `uvicorn`, `sqlalchemy[asyncio]`, `alembic`, `authlib`, `httpx`, plus OS packages `tesseract-ocr`, `tesseract-ocr-spa`, `tesseract-ocr-eng`, `libmagic1`, `poppler-utils`. Three containers from this image, distinguished by entrypoint:
     - `api`: `uvicorn buscasam.api.main:app --host 0.0.0.0 --port 8000`
     - `worker_default`: `procrastinate --app=buscasam.core.jobs.app worker --queues=default --concurrency=8`
     - `worker_ocr`: `procrastinate --app=buscasam.core.jobs.app worker --queues=ocr --concurrency=1`
   - `frontend/Dockerfile` — Node image (LTS pinned via `.nvmrc`). Multi-stage build producing `output: 'standalone'`. Entrypoint: `node server.js`.

   Three external images pinned by digest: `pgvector/pgvector:pg16@sha256:…`, `ghcr.io/huggingface/text-embeddings-inference:cpu-…@sha256:…`, `nginx:1.27-alpine@sha256:…`.

3. Reverse proxy: nginx.

   - `:80` always listening. In `TLS_MODE=upstream`, serves the app directly and trusts `X-Forwarded-Proto` / `X-Forwarded-For` from a single configured upstream CIDR. In `TLS_MODE=self`, returns 301 to `:443`.
   - `:443` only listening in `TLS_MODE=self`. Mounts `/etc/letsencrypt/` from a `certbot` sidecar.
   - Two upstreams: `backend:8000` (for `location /api/`) and `frontend:3000` (everything else).
   - `location /_blobs/ { internal; alias /var/lib/buscasam/blobs/; sendfile on; tcp_nopush on; }` — verbatim from ADR-0006 §9. `blobs/` mount shared read-only with nginx.
   - `client_max_body_size 70m`.

4. Service layout (steady-state graph):

   | Service | Image | Entrypoint | Persistent mounts | Restart |
   |---|---|---|---|---|
   | `db` | `pgvector/pgvector:pg16` | postgres default | `/var/lib/buscasam/postgres → PGDATA` | `unless-stopped` |
   | `tei` | TEI CPU pinned | `text-embeddings-router --model-id … --revision … --port 80` | `/var/lib/buscasam/tei-cache → /data` | `unless-stopped` |
   | `api` | `backend` | `uvicorn …` | `blobs` (rw), `tmp` (rw) | `unless-stopped` |
   | `worker_default` | `backend` | `procrastinate worker --queues=default --concurrency=8` | `blobs` (rw), `tmp` (rw) | `unless-stopped` |
   | `worker_ocr` | `backend` | `procrastinate worker --queues=ocr --concurrency=1` | `blobs` (rw), `tmp` (rw) | `unless-stopped` |
   | `frontend` | `frontend` | `node server.js` | — | `unless-stopped` |
   | `nginx` | `nginx:1.27-alpine` | nginx default | `blobs` (ro), `/etc/nginx/conf.d` (config), `/etc/letsencrypt` (in `self`) | `unless-stopped` |
   | `backup` | `postgres:16` + `rsync` | sleep-loop wrapper around `pg_dump` + `rsync` | `blobs` (ro), `/backup/buscasam` (rw) | `unless-stopped` |
   | `certbot` (`self` only) | `certbot/certbot` | `certonly --webroot --renew-by-default` cron | `/etc/letsencrypt` (rw), `/var/www/certbot` (rw) | `unless-stopped` |
   | `migrate` (`run --rm`) | `backend` | `bash -c 'alembic upgrade head && procrastinate schema --apply'` | — | `"no"` |

5. Healthchecks and `depends_on`.

   - `db`: `pg_isready -U buscasam -d buscasam`, 5 s interval, 5 retries.
   - `tei`: `curl -fsS http://localhost/health`, 10 s.
   - `api`: `curl -fsS http://localhost:8000/health` (process-liveness only, no DB ping).
   - `frontend`: `curl -fsS http://localhost:3000/`.
   - `nginx`, `worker_default`, `worker_ocr`, `backup`: no healthcheck.
   - `depends_on`:
     - `api`, `worker_default`, `worker_ocr` → `db (service_healthy)`, `tei (service_healthy)`.
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
   │   └── .tmp/        ← in-flight uploads
   ├── tei-cache/       ← pre-staged HF model
   └── tmp/             ← FastAPI multipart parking; same FS as blobs/ for atomic rename
   /backup/buscasam/    ← bind to whatever UNSAM provides; see §11
   ├── db/              ← pg_dump archives, 14-day rotation
   └── blobs/           ← rsync mirror of /var/lib/buscasam/blobs/
   ```

   No Docker named volumes.

8. Configuration: single `.env` on the VM. `compose.prod.yaml` loads `./.env` (mode 0600, gitignored) via `env_file:` per service, with per-service `environment:` allowlist. Repo ships `.env.example`. CI runs `python -m buscasam.config check-example` which loads the `Settings` schema and asserts every field appears in `.env.example`.

   - Secrets: `POSTGRES_PASSWORD`, `SESSION_SECRET_KEY` (ADR-0005 §4 `itsdangerous`), `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `SMTP_USERNAME`, `SMTP_PASSWORD`.
   - Non-secret: `BUSCASAM_BASE_URL`, `TLS_MODE`, `EMBEDDING_MODEL_REVISION`, `EXTRACT_PIPELINE_VERSION`, `OCR_QUEUE_THRESHOLD_BYTES`, `BACKUP_RETENTION_DAYS`.

   Rotation = edit `.env` and `docker compose up -d`.

9. TLS: two-mode nginx config, selected by `TLS_MODE`.

   - `TLS_MODE=upstream`: nginx listens `:80` only; trusts `X-Forwarded-Proto` / `X-Forwarded-For` from a single configured upstream CIDR (`TRUSTED_PROXY_CIDR` in `.env`); FastAPI marks cookies `Secure` from the forwarded scheme.
   - `TLS_MODE=self`: nginx listens `:80` (HTTP→HTTPS 301 + `.well-known/acme-challenge/`) and `:443` (full TLS); `certbot` sidecar runs `certonly --webroot --renew-by-default` on a 12-hour loop; nginx reload via shared `/etc/letsencrypt/` + a daily forced reload.
   - Both modes ship in the image; the active one is selected at container start by an entrypoint script that templates `nginx.conf` from `nginx.conf.template`.

10. TEI model pre-staging. First-time setup (`scripts/prestage_model.sh`, committed): from a workstation with `huggingface.co` reachability, download the pinned revision SHA, tar, scp to the VM, extract to `/var/lib/buscasam/tei-cache/`. TEI starts with `HF_HUB_OFFLINE=1` and explicit `--revision`. If cache is missing or revision-mismatched, the container exits non-zero. Tokenizer file vendored in the repo; startup assertion in `core/embed.py` refuses on mismatch. Model bump = re-run pre-staging script before deploy.

11. Backup execution: sidecar container, priority-list destination. The `backup` service is `postgres:16` with `rsync` apt-installed; entrypoint:

    ```bash
    while true; do
      ts=$(date -u +%FT%H%MZ)
      pg_dump -h db -U "$POSTGRES_USER" -Fc "$POSTGRES_DB" > "/backup/buscasam/db/buscasam-$ts.dump"
      find /backup/buscasam/db -name 'buscasam-*.dump' -mtime +"$BACKUP_RETENTION_DAYS" -delete
      rsync -a --delete /var/lib/buscasam/blobs/ /backup/buscasam/blobs/
      sleep 86400
    done
    ```

    `BACKUP_RETENTION_DAYS=14` default; blob mirror has no rotation. `/backup/buscasam/` destination resolves in priority order at setup time:
    1. UNSAM-provided off-host mount (real DR).
    2. Separate disk on the VM (same-VM redundancy).
    3. Same disk under `/var/backup/buscasam/` (no redundancy).

12. Deploy via `scripts/deploy.sh`:

    ```bash
    set -euo pipefail
    cd /opt/buscasam
    git fetch --tags
    git checkout "${1:-main}"
    docker compose -f compose.prod.yaml build
    docker compose -f compose.prod.yaml up -d db
    docker compose -f compose.prod.yaml run --rm migrate
    docker compose -f compose.prod.yaml up -d
    docker image prune -f
    ```

    A failed `migrate` exits non-zero before `up -d`, leaving the previous container generation serving. Rollback = `git checkout <prev-tag> && scripts/deploy.sh <prev-tag>`. CI runs tests and the OpenAPI codegen diff check but does NOT build or push images.

13. Schema apply: `migrate` runs `alembic upgrade head && procrastinate schema --apply`. The first Alembic migration executes `CREATE EXTENSION IF NOT EXISTS vector;`, `CREATE EXTENSION IF NOT EXISTS unaccent;`, `CREATE EXTENSION IF NOT EXISTS ltree;`, and the `CREATE TEXT SEARCH CONFIGURATION es_unaccent …` from ADR-0001 §8. No other extensions.

14. Resource caps. Compose `mem_limit:` on exactly two services: `tei: 3g`, `worker_ocr: 2g`. All other services uncapped. `db` carries `oom_score_adj: -500`. Postgres' own memory tuning (`shared_buffers`, `work_mem`, `maintenance_work_mem`, `effective_cache_size`) lives in a mounted `postgresql.conf`, not in compose limits.

15. Logging: capped `json-file` driver via YAML anchor in `compose.prod.yaml`:

    ```yaml
    x-logging: &default-logging
      driver: json-file
      options:
        max-size: "10m"
        max-file: "5"
    ```

    applied to every long-running service. App processes write structured JSON to stdout. No host-side log shipping at MVP; `docker compose logs <svc>` is the operator surface.

16. Rate limiting at nginx. Two `limit_req` zones in `nginx.conf`:

    - `auth_zone` keyed on `$binary_remote_addr`, 10 req/min burst 20 — applied to `/api/auth/login` and `/api/auth/google/callback`.
    - `guest_zone` keyed on `$binary_remote_addr`, 60 req/min burst 120 — applied to `/api/search` and `/api/docs/*/download` when the request has no `sid` cookie; authenticated users bypass via `if ($cookie_sid)`.

17. GPU upgrade path. Change the `image:` digest of `tei` and add `deploy.resources.reservations.devices: [driver: nvidia, count: all, capabilities: [gpu]]` (plus host-side NVIDIA Container Toolkit). All other services unaffected. Reversible.

## Open dependencies on UNSAM IT

- **DNS A record** for `buscasam.unsam.edu.ar` (or chosen hostname) pointing at the VM.
- **TLS topology confirmation:** UNSAM terminates TLS upstream (`TLS_MODE=upstream`) or we own certs (`TLS_MODE=self` + outbound to Let's Encrypt + inbound on `:80` for HTTP-01).
- **Outbound HTTPS** from the VM to `pypi.org`, `registry.npmjs.org`, `ghcr.io`, `github.com` (build-time).
- **One-time outbound** to `huggingface.co` from any workstation that can scp to the VM (pre-staging §10).
- **Backup mount:** off-host storage if available; otherwise same-VM redundancy.
- **Root or sudo on the VM** for first-time host setup (creating `buscasam:buscasam`, installing Docker, creating `/var/lib/buscasam/` and `/backup/buscasam/`).
- **Google Cloud OAuth client** scoped to the UNSAM Workspace tenants.
