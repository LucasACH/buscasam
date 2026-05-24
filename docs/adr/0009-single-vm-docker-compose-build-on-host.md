# Single-VM Docker Compose topology, built on the host, defensive UNSAM provisioning

## Status

Accepted

## Decision

BUSCASAM runs as a single Docker Compose stack on one UNSAM-provisioned VM, in both dev and prod, with the prod variant differing only by overrides (build mode, hot-reload flags, exposed ports). Two Dockerfiles are owned in-repo — `backend/Dockerfile` (Python; serves three containers `api` / `worker_default` / `worker_ocr` with different entrypoints, per ADR-0003 §5) and `frontend/Dockerfile` (Node standalone, per ADR-0004 §1) — and three external images are pinned by digest: `pgvector/pgvector:pg16` (ADR-0001 §1), the TEI CPU image (ADR-0002 §2), and the chosen nginx image. Reverse proxy is **nginx** (locked, not Caddy — ADR-0006 §9's `X-Accel-Redirect` is nginx-specific, closing ADR-0004 §2's open question). Images are built on the VM from a `git pull`, not pulled from a registry: deploy is a committed `scripts/deploy.sh` that runs `git pull && docker compose build && docker compose up -d db && docker compose run --rm migrate && docker compose up -d`, where `migrate` is a one-shot container that runs `alembic upgrade head && procrastinate schema --apply` (ADR-0008 §10) and whose failure blocks the rest of `up -d`. All persistent state lives under `/var/lib/buscasam/` as host bind mounts (`postgres/`, `blobs/`, `tei-cache/`, `tmp/`), matching ADR-0006 §1's already-named `blobs/` path and giving `pg_dump`, `rsync`, and ops `ls`/`du` direct visibility. Secrets are a single `.env` (mode 0600) next to the prod compose file, gitignored, with `.env.example` committed and a CI check that the example covers every `Settings` field. TLS terminates in two selectable modes via a single `TLS_MODE` env var: `upstream` (nginx on `:80`, trusts `X-Forwarded-Proto` from an UNSAM-managed LB) or `self` (nginx on `:443` with a `certbot/certbot` sidecar managing a Let's Encrypt cert via HTTP-01); both modes ship and the active one is selected at deploy time. The TEI model is **pre-staged** on the VM filesystem (downloaded once from a workstation with HF reachability, scp'd into `/var/lib/buscasam/tei-cache/`) and TEI runs with `HF_HUB_OFFLINE=1` so a runtime HF outage cannot silently degrade indexing or search. Backups are a sidecar container (`postgres:16` base, internal sleep-loop scheduler) that runs daily at 03:00: `pg_dump -Fc` into `/backup/buscasam/db/` with 14-day rotation, plus `rsync --delete /var/lib/buscasam/blobs/ /backup/buscasam/blobs/` per ADR-0006 §13. The `/backup/` mount is a bind mount populated by whatever UNSAM provides (off-host storage if they grant it, separate disk otherwise, same disk under `/var/backup/buscasam/` as a last resort — same posture as ADR-0001 §1's `pg_dump`). The worker topology from ADR-0008 §2 lands as two distinct compose services (`worker_default`, `worker_ocr`), not as replicas of one service, preserving independent restart and resource ceilings. Memory caps are set on `tei` (3 GB) and `worker_ocr` (2 GB) and nowhere else; Postgres' OOM score is biased with `oom_score_adj: -500` so the kernel picks any other process before evicting the database. Observability beyond Docker's `json-file` log driver (capped 10 MB × 5 files per container) and ADR-0008 §9's structured stdout logs is **explicitly deferred to ADR-#10** — this ADR ships a topology that an observability sidecar can be added to without restructuring services.

## Context

ADR-0001 commits to a single VM with daily `pg_dump`, names `docker-compose` as the dev/prod runtime for pgvector, and pins pgvector ≥ 0.8 by container. ADR-0002 pins the TEI sidecar by image digest, names a vendored tokenizer file and a single-source-of-truth `EMBEDDING_MODEL_REVISION`, and flags GPU as a future image-tag swap. ADR-0003 commits to one image for API + worker sharing `core/`, with the queue as the only seam between processes. ADR-0004 picks Next.js with `output: 'standalone'`, mandates a same-origin reverse proxy splitting `/api/*` from HTML routes, and explicitly defers the proxy choice (and SSO-callback origin question, since closed by ADR-0005) to "ADR-#9". ADR-0005 lands the OAuth callback on FastAPI at `/api/auth/google/callback`, requires `HttpOnly; Secure; SameSite=Lax` cookies (so TLS is non-negotiable for prod), and defers rate limiting to ADR-#9 as a proxy concern. ADR-0006 specifies `/var/lib/buscasam/blobs/` as the blob mount, requires nginx for `X-Accel-Redirect`, and explicitly states "Dev environments run nginx via docker-compose to match prod's auth-then-redirect flow." ADR-0007 fixes a single `index_document` job whose worst case is ~30 minutes of CPU OCR. ADR-0008 picks procrastinate with two worker processes and explicitly defers the supervisor choice to ADR-#9, also assigning operator observability to ADR-#9. UNSAM IT has not been consulted on what the prod host actually looks like: the team has no confirmed answer on root access, OS, Docker version, outbound network allowlist, TLS topology, DNS authority, or backup mount provisioning. The decision to be made: a deploy topology that survives the realistic worst case (managed VM, narrow outbound allowlist, no host-cron access, no separate backup mount) without being needlessly heavy for the realistic best case (root VM with Docker and reasonable internet), in both dev and prod, for a small team of ~3 Python+TypeScript developers on UNSAM on-prem hardware.

## Considered options

- **Kubernetes (k3s or full).** Rejected: a 16 GB single-VM deploy hosting one application is wildly under the regime k8s pays back in. Adds an etcd, an api-server, a CNI, controllers, and a learning curve — for an app whose worker count is 2 and whose service count is 8. Revisit if UNSAM ever offers a managed cluster and the system needs multi-host scaling, both of which are beyond this ADR's planning horizon.
- **Plain systemd units on the host.** Rejected: defensive design says we cannot assume root or systemd write access; ADRs 0001, 0002, 0004, 0006 have already committed to specific container images pinned by digest; reproducing the TEI runtime as a systemd unit would force us to either install a Python ML stack on the host or wrap the official TEI image in a `Type=forking` unit that calls `docker run`, gaining nothing over compose. The premise — "one fewer indirection" — collapses because the containers exist either way.
- **Hybrid: containers for `db` + `tei`, app processes as systemd.** Rejected on dev/prod-parity grounds: dev would run `uvicorn` natively on a Mac, prod under systemd on Linux, both against Linux-only deps (`tessdata`, `libmagic`, `pdfminer.six` system libs) — a recipe for "works on my machine" bugs at the file-extraction layer. Also assumes the systemd write access defensive design rules out.
- **`docker-compose` with images pulled from GHCR.** Rejected at MVP: assumes outbound to `ghcr.io` and a stable PAT on the VM, both of which are unconfirmed under "design defensively." The savings (~3–5 min faster deploys, immutable artifact rollback) do not pay back at weekly deploy frequency for a 3-person team. Trivially upgradeable later: a CI step that builds and pushes, plus `image:` lines in compose, leaves feature code untouched.
- **Self-hosted container registry on the VM.** Rejected: another stateful service to operate for marginal benefit.
- **Stateful-services-only compose + native app processes in dev.** Rejected as the dev shape: ADR-0006 §9 already commits to nginx-in-compose in dev to exercise `X-Accel-Redirect`; once that container is there, putting api/worker/frontend in compose costs nothing extra and the iteration-speed loss on macOS bind mounts is small (`uvicorn --reload` and `next dev` HMR both work through Docker for Mac's VirtioFS at acceptable latency for a small codebase).
- **Caddy instead of nginx.** Rejected after the fact: ADR-0004 §2 left this open, but ADR-0006 §9's `X-Accel-Redirect` and `internal;` location pattern are nginx-specific. Switching to Caddy would force a different `auth-then-stream` mechanism (`reverse_proxy` with body buffering, or a request-rewriting plugin) — extra engineering for auto-TLS, which we can get from the `certbot` sidecar at lower architectural cost.
- **Docker secrets (`secrets:` block) instead of `.env`.** Rejected at this scale: six secrets in a single-VM deploy do not justify the `*_FILE` convention plumbing in `pydantic-settings`. Revisit if the secret count grows past ~15 or if multi-host topology is ever a goal.
- **HashiCorp Vault / sops / external secret manager.** Rejected: another stateful service or external dependency for six secrets.
- **Pulling the TEI model on first container start.** Rejected: assumes outbound to `huggingface.co` from the VM (unconfirmed under defensive design); first-deploy includes a 2 GB blocking download; an HF outage mid-deploy is fatal; HF Hub's "latest cached" fallback can silently desync from the tokenizer revision and break ADR-0002 §5's single-source-of-truth invariant.
- **Baking the TEI model into a custom TEI image.** Rejected: image bloats past 2 GB, deploy-time pull is slow, and upstream TEI does not ship model-baked images for the same reason.
- **Host crontab for backups.** Rejected: assumes root crontab write access; backup definition lives in two places (compose + crontab); failure visibility moves outside `docker compose logs`.
- **Backup as a procrastinate periodic job.** Rejected: ADR-0008 §1 deliberately keeps `@app.periodic` unused so periodic capability is a deliberate adoption, not a quiet drift; backup is an ops concern, not application work.
- **A `migrate` service inside the steady-state compose graph (with `service_completed_successfully` gating).** Rejected as the migration shape: a partially-failed migration leaves the stack in an ambiguous half-up state and the troubleshooting UX is "dig through `compose logs migrate`." An explicit deploy-script step (`run --rm migrate`) blocks deploy on migration failure with a clean exit code, and the old stack keeps serving in the meantime.
- **Docker named volumes for all stateful paths.** Rejected: ADR-0006 §1 already locks `/var/lib/buscasam/blobs/` as a known host path; staying consistent (everything under `/var/lib/buscasam/`) means one mental model for "where is the data?" instead of two (some named, some bind).
- **`mem_limit` on every container.** Rejected: doubles the tuning surface; tight caps on Postgres conflict with pgvector HNSW's iterative-scan memory profile (ADR-0001 §5) and can produce surprising query failures rather than the OOM-kill they're meant to prevent. Capping only `tei` and `worker_ocr` (the two with legitimate runaway scenarios) covers the failure modes that matter.
- **TLS always self-terminated with certbot.** Rejected: breaks if UNSAM ever decides to put their own reverse proxy in front of us (likely, for a `.unsam.edu.ar` hostname); two-encrypted-hops is the typical observed failure mode.
- **TLS always upstream-terminated.** Rejected: assumes UNSAM provides upstream TLS day one; if they don't, the OAuth callback (ADR-0005) cannot register an HTTPS `redirect_uri` and the SSO flow never works.
- **Defer TLS, ship HTTP only first.** Rejected: ADR-0005 requires `Secure` cookies, Google requires HTTPS `redirect_uri` in production OAuth client config. Plaintext is a non-starter for any prod-shaped deploy.
- **Skip `oom_score_adj` biasing on Postgres.** Rejected: under memory pressure the kernel's default OOM victim selection can pick Postgres (large RSS); Postgres dying mid-search is much worse than `worker_ocr` dying mid-job (which procrastinate retries per ADR-0008 §5).

## Architecture decisions locked by this ADR

1. **Runtime: one Docker Compose stack, dev and prod.** `compose.yaml` (dev), `compose.prod.yaml` (prod overrides — build mode instead of bind-mount source, no host-port exposure on `db`, prod-grade nginx config, `certbot` sidecar conditionally enabled). Both files describe the same eight services: `db`, `tei`, `api`, `worker_default`, `worker_ocr`, `frontend`, `nginx`, `backup`. A ninth service `migrate` exists in both files but is only ever invoked via `docker compose run --rm migrate`, never started by `up`. Closes ADR-0001 §1, ADR-0004 §2, ADR-0006 §9, ADR-0008 §2.

2. **Two Dockerfiles owned in-repo.**
   - `backend/Dockerfile` — Python image. Installs Poetry/uv-resolved deps including `pdfminer.six`, `ocrmypdf`, `python-docx`, `odfpy`, `yake`, `procrastinate`, `fastapi`, `uvicorn`, `sqlalchemy[asyncio]`, `alembic`, `authlib`, `httpx`, plus OS packages `tesseract-ocr`, `tesseract-ocr-spa`, `tesseract-ocr-eng`, `libmagic1`, `poppler-utils`. Serves three containers from this image, distinguished only by entrypoint:
     - `api`: `uvicorn buscasam.api.main:app --host 0.0.0.0 --port 8000`
     - `worker_default`: `procrastinate --app=buscasam.jobs.app worker --queues=default --concurrency=8`
     - `worker_ocr`: `procrastinate --app=buscasam.jobs.app worker --queues=ocr --concurrency=1`
   - `frontend/Dockerfile` — Node image (LTS pinned via `.nvmrc`, ADR-0004 §11). Multi-stage build producing the `output: 'standalone'` artifact (ADR-0004 §1). Single entrypoint: `node server.js`.

   Three external images pinned by digest: `pgvector/pgvector:pg16@sha256:…`, `ghcr.io/huggingface/text-embeddings-inference:cpu-…@sha256:…`, `nginx:1.27-alpine@sha256:…`.

3. **Reverse proxy: nginx, locked.** Closes ADR-0004 §2. `nginx` service config:
   - `:80` always listening. In `TLS_MODE=upstream`, serves the app directly and trusts `X-Forwarded-Proto`/`X-Forwarded-For` from a single configured upstream CIDR. In `TLS_MODE=self`, returns 301 to `:443`.
   - `:443` only listening in `TLS_MODE=self`. Mounts `/etc/letsencrypt/` from a `certbot` companion sidecar.
   - Two upstreams: `backend:8000` (for `location /api/`) and `frontend:3000` (for everything else). Path-prefix routing per ADR-0004 §2.
   - `location /_blobs/ { internal; alias /var/lib/buscasam/blobs/; sendfile on; tcp_nopush on; }` — verbatim from ADR-0006 §9. The `blobs/` mount is shared read-only with the nginx container.
   - `client_max_body_size 70m` to permit ADR-0006 §10's 50 MB main + 20 MB attachment payloads with headroom.

4. **Service layout in compose (steady-state graph).**

   | Service | Image | Entrypoint summary | Persistent mounts | Restart |
   |---|---|---|---|---|
   | `db` | `pgvector/pgvector:pg16` | postgres default | `/var/lib/buscasam/postgres → PGDATA` | `unless-stopped` |
   | `tei` | TEI CPU pinned | `text-embeddings-router --model-id … --revision … --port 80` | `/var/lib/buscasam/tei-cache → /data` | `unless-stopped` |
   | `api` | `backend` (owned) | `uvicorn …` | `/var/lib/buscasam/blobs` (rw), `/var/lib/buscasam/tmp` (rw) | `unless-stopped` |
   | `worker_default` | `backend` (owned) | `procrastinate worker --queues=default --concurrency=8` | `/var/lib/buscasam/blobs` (rw), `/var/lib/buscasam/tmp` (rw) | `unless-stopped` |
   | `worker_ocr` | `backend` (owned) | `procrastinate worker --queues=ocr --concurrency=1` | `/var/lib/buscasam/blobs` (rw), `/var/lib/buscasam/tmp` (rw) | `unless-stopped` |
   | `frontend` | `frontend` (owned) | `node server.js` | — | `unless-stopped` |
   | `nginx` | `nginx:1.27-alpine` | nginx default | `/var/lib/buscasam/blobs` (ro), `/etc/nginx/conf.d` (config), `/etc/letsencrypt` (in `self` mode) | `unless-stopped` |
   | `backup` | `postgres:16` (+ apt `rsync`) | sleep-loop wrapper around `pg_dump` + `rsync` | `/var/lib/buscasam/blobs` (ro), `/backup/buscasam` (rw) | `unless-stopped` |
   | `certbot` (`self` only) | `certbot/certbot` | `certonly --webroot --renew-by-default` cron | `/etc/letsencrypt` (rw), `/var/www/certbot` (rw) | `unless-stopped` |
   | `migrate` (`run --rm`) | `backend` (owned) | `bash -c 'alembic upgrade head && procrastinate schema --apply'` | — | `"no"` |

5. **Healthchecks and `depends_on` conditions.**
   - `db`: `pg_isready -U buscasam -d buscasam`, 5 s interval, 5 retries.
   - `tei`: `curl -fsS http://localhost/health`, 10 s interval.
   - `api`: `curl -fsS http://localhost:8000/health` (new endpoint, returns 200 unconditionally — process-liveness only, no DB ping).
   - `frontend`: `curl -fsS http://localhost:3000/`.
   - `nginx`, `worker_default`, `worker_ocr`, `backup`: no healthcheck. Workers explicitly skipped per ADR-0008 §9 (operator observability is ADR-#10); nginx and backup rely on `restart: unless-stopped`.
   - `depends_on`:
     - `api`, `worker_default`, `worker_ocr` → `db (service_healthy)`, `tei (service_healthy)`.
     - `nginx` → `api (service_started)`, `frontend (service_started)`. Deliberately `service_started`, not `service_healthy`: nginx returning 502 briefly during an API restart is preferable to nginx refusing new connections.
     - `frontend` → no compose dep on `api`; the network path goes through nginx, which mediates timing.
     - `migrate` (when invoked via `run --rm`) → `db (service_healthy)`.

6. **Port exposure (host ↔ container).**
   - **Prod:** `nginx` binds `0.0.0.0:80` and `0.0.0.0:443`. No other service binds a host port.
   - **Dev (`compose.yaml` override):** additionally binds `db` to `127.0.0.1:5432` for host-side `psql` and ad-hoc Alembic invocations from the workstation. No other service is exposed.

7. **Persistent state — bind mounts under `/var/lib/buscasam/`.** Owned by a host system user `buscasam:buscasam` (uid/gid configurable via build args). Layout:

   ```
   /var/lib/buscasam/
   ├── postgres/        ← db PGDATA
   ├── blobs/           ← ADR-0006 §1
   │   ├── ab/cd/…      ← sharded sha256 (ADR-0006 §2)
   │   └── .tmp/        ← in-flight uploads (ADR-0006 §4)
   ├── tei-cache/       ← pre-staged HF model (see §10)
   └── tmp/             ← FastAPI multipart parking; same FS as blobs/ for atomic rename
   /backup/buscasam/    ← bind to whatever UNSAM provides; see §11
   ├── db/              ← pg_dump archives, 14-day rotation
   └── blobs/           ← rsync mirror of /var/lib/buscasam/blobs/
   ```

   Closes ADR-0006 §1's path commitment for the rest of the stack. No Docker named volumes are used.

8. **Configuration: single `.env` on the VM.** `compose.prod.yaml` loads `./.env` (mode 0600, gitignored) via `env_file:` per service, with each service receiving only the subset of keys it needs (Compose `environment:` allowlist per service). The repo ships `.env.example` documenting every required key. CI runs `python -m buscasam.config check-example` which loads the `Settings` schema (ADR-0003 §7) and asserts every field appears in `.env.example`. Secrets in scope at MVP: `POSTGRES_PASSWORD`, `SESSION_SECRET_KEY` (ADR-0005 §4 `itsdangerous`), `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `SMTP_USERNAME`, `SMTP_PASSWORD`. Non-secret env: `BUSCASAM_BASE_URL`, `TLS_MODE`, `EMBEDDING_MODEL_REVISION`, `EXTRACT_PIPELINE_VERSION`, `OCR_QUEUE_THRESHOLD_BYTES`, `BACKUP_RETENTION_DAYS`. Rotation = edit `.env` and `docker compose up -d`.

9. **TLS: two-mode nginx config, selected by `TLS_MODE`.**
   - `TLS_MODE=upstream`: nginx listens `:80` only; trusts `X-Forwarded-Proto`/`X-Forwarded-For` from a single configured upstream CIDR (`TRUSTED_PROXY_CIDR` in `.env`); FastAPI marks cookies `Secure` based on the forwarded scheme.
   - `TLS_MODE=self`: nginx listens `:80` (HTTP→HTTPS 301 + `.well-known/acme-challenge/`) and `:443` (full TLS); `certbot` sidecar runs `certonly --webroot --renew-by-default` on a 12-hour loop; renewal triggers nginx reload via shared `/etc/letsencrypt/` + an `inotify` watcher on the nginx container, or a daily forced reload (simpler, acceptable downtime).
   - Both modes ship in the image; the active one is selected at container start by an entrypoint script that templates `nginx.conf` from `nginx.conf.template`. Mode change = `.env` edit + `docker compose up -d nginx`.

10. **TEI model pre-staging.** First-time setup (`scripts/prestage_model.sh`, committed): from a workstation with `huggingface.co` reachability, download the pinned revision SHA into a local cache, tar it, scp to the VM, extract to `/var/lib/buscasam/tei-cache/`. TEI container starts with `HF_HUB_OFFLINE=1` and the explicit `--revision` flag; if the cache is missing or revision-mismatched, the container exits non-zero at start (clean error, not silent degradation). Tokenizer file revision (ADR-0002 §5) is vendored in the repo; a startup assertion in `core/embed.py` (ADR-0002 §3) reads both revisions and refuses to run on mismatch. Model bump (ADR-0002 §6) = re-run pre-staging script before deploy.

11. **Backup execution: sidecar container, priority-list destination.** The `backup` service is `postgres:16` with `rsync` apt-installed; entrypoint is a tight bash loop:
    ```bash
    while true; do
      ts=$(date -u +%FT%H%MZ)
      pg_dump -h db -U "$POSTGRES_USER" -Fc "$POSTGRES_DB" > "/backup/buscasam/db/buscasam-$ts.dump"
      find /backup/buscasam/db -name 'buscasam-*.dump' -mtime +"$BACKUP_RETENTION_DAYS" -delete
      rsync -a --delete /var/lib/buscasam/blobs/ /backup/buscasam/blobs/
      sleep 86400
    done
    ```
    `BACKUP_RETENTION_DAYS=14` default; blob mirror has no rotation per ADR-0006 §13. `/backup/buscasam/` destination resolves in priority order at setup time:
    1. UNSAM-provided off-host mount (real DR).
    2. Separate disk on the VM (same-VM redundancy, defends against application bugs and `rm -rf`).
    3. Same disk under `/var/backup/buscasam/` (no redundancy; the `pg_dump`-on-same-disk posture from ADR-0001 §1).

    The active choice is bound by the bind mount in `compose.prod.yaml`; the ADR consequences below name (3) explicitly as "not DR."

12. **Deploy mechanism: build on the VM via `scripts/deploy.sh`.** No image registry. Committed script:
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
    A failed `migrate` step exits non-zero before `up -d`, leaving the previous container generation serving. Rollback = `git checkout <prev-tag> && scripts/deploy.sh <prev-tag>`. CI runs tests and the OpenAPI codegen diff check (ADR-0004 §10) but does not build or push images.

13. **Schema apply: one explicit step, idempotent both sides.** The `migrate` one-shot runs `alembic upgrade head && procrastinate schema --apply` (closes ADR-0008 §10). The very first Alembic migration in repo history executes `CREATE EXTENSION IF NOT EXISTS vector;`, `CREATE EXTENSION IF NOT EXISTS unaccent;`, `CREATE EXTENSION IF NOT EXISTS ltree;`, `CREATE EXTENSION IF NOT EXISTS pg_trgm;`, and the `CREATE TEXT SEARCH CONFIGURATION es_unaccent …` from ADR-0001 §8 — so extension provisioning and the FTS config are part of the regular migration stream, not a separate manual step.

14. **Resource caps and OOM bias.** Compose `mem_limit:` on exactly two services: `tei: 3g`, `worker_ocr: 2g`. All other services uncapped (kernel OOM is the last-line defense). `db` carries `oom_score_adj: -500` so the kernel preferentially evicts any other process before Postgres under memory pressure. Postgres' own memory tuning (`shared_buffers`, `work_mem`, `maintenance_work_mem`, `effective_cache_size`) is the correct knob for the DB and lives in a mounted `postgresql.conf`, not in compose limits.

15. **Logging: capped `json-file` driver, structured stdout.** A YAML anchor in `compose.prod.yaml`:
    ```yaml
    x-logging: &default-logging
      driver: json-file
      options:
        max-size: "10m"
        max-file: "5"
    ```
    applied to every long-running service. App processes write structured JSON to stdout (uvicorn `--log-config` for the API, procrastinate's stdout logger for workers — ADR-0008 §9). No host-side log shipping at MVP; `docker compose logs <svc>` is the operator surface.

16. **Rate limiting at nginx (closes ADR-0005 §16).** Two `limit_req` zones in `nginx.conf`:
    - `auth_zone` keyed on `$binary_remote_addr`, 10 req/min burst 20 — applied to `/api/auth/login` and `/api/auth/google/callback`. Defends against OAuth-flow abuse.
    - `guest_zone` keyed on `$binary_remote_addr`, 60 req/min burst 120 — applied to `/api/search` and `/api/docs/*/download` when the request has no `sid` cookie. Defends against `público`-content scraping bursts; authenticated users bypass via an `if ($cookie_sid)` exclusion. Starting values are conservative guesses; ADR-#10 picks the metrics that recalibrate them.

17. **GPU upgrade path (no decision, hook documented).** ADR-0002 §7 reserves the right to swap TEI to a GPU image tag. From this ADR's perspective: change the `image:` digest of `tei` and add `deploy.resources.reservations.devices: [driver: nvidia, count: all, capabilities: [gpu]]` (plus the host-side NVIDIA Container Toolkit). All other services are unaffected. The change is reversible by reverting the compose diff.

## Consequences

- **Defensive posture trades deploy speed for unknown-host survivability.** Build-on-VM and pre-staged-model both add minutes to first-deploy and any model bump, in exchange for surviving narrow UNSAM outbound network policies that we have no commitment from IT to relax. If UNSAM later confirms generous outbound and provides a registry, the upgrade path is documented (build in CI, push to GHCR, change `image:` lines) and surgical — `core/` and feature code are untouched.
- **Single VM = single point of failure.** All real failure modes (disk, host kernel, power, network) take the application down. RPO is up to 24 h (last backup cron); RTO is hours (manual rebuild from backup onto a new VM). This matches the operational ambition implied by ADR-0001's `pg_dump` and ADR-0006's `rsync` postures; it is not real disaster recovery. The day UNSAM provisions off-host backup storage, RPO becomes meaningful in a way it currently is not.
- **`/backup/` priority-list (§11.3) is honest about its bottom rung.** If UNSAM gives us nothing, "backup" is same-disk redundancy — protection against `rm -rf` typos and application bugs, not against the disk itself dying. The ADR-0006 §13 wording is consistent ("same-VM redundancy, matching the `pg_dump` posture"); flagged here so it isn't mistaken for off-host DR.
- **Two-mode TLS doubles the nginx config surface.** Templating `nginx.conf` from a small fragment library keeps the duplication contained, but a future contributor maintaining nginx config needs to remember the toggle exists. Mitigation: a CI smoke step (`scripts/check_nginx_configs.sh`) renders both modes and runs `nginx -t` against each.
- **TEI model bump becomes a coordinated three-step operation.** Update `EMBEDDING_MODEL_REVISION` in `.env`, re-run `scripts/prestage_model.sh` against the VM (downloads fresh cache, scp's it), then deploy. ADR-0002 §6's "deliberate maintenance window" posture absorbs this; the alternative (download-on-start) trades operator burden for invisible-failure risk.
- **Build-on-VM means the prod VM needs ~2 GB of free disk for Docker build cache** plus the working images. At 16 GB RAM and modest disk, this is comfortable but not invisible — `docker image prune -f` at the end of every deploy keeps cache bounded. A deploy that fills `/var/lib/docker` would surface as a Docker daemon error before any application impact.
- **`docker compose run --rm migrate` is the deploy contract.** A contributor who runs `docker compose up -d` directly during an emergency, bypassing the script, can leave the API up against an un-migrated DB (runtime errors from missing tables/columns). The mitigation is the script being the only documented deploy path; `scripts/deploy.sh` is the contract, not "compose itself."
- **Bind-mount UID/GID alignment is a one-time setup cost.** The `buscasam:buscasam` system user on the host owns `/var/lib/buscasam/*`; container images are built with a matching uid (build arg). A host with a different uid for that user breaks file ownership in a way that surfaces as Postgres refusing to start or FastAPI failing to write `blobs/.tmp/`. Documented in the setup runbook; not a recurring cost.
- **Worker containers don't auto-reload on code change in dev.** `uvicorn --reload` and `next dev` HMR cover api and frontend; procrastinate workers reload only on `docker compose restart worker_default worker_ocr`. Acceptable: indexing-pipeline changes are tested via integration tests against a real DB before being exercised through the worker.
- **Rate limiting is a coarse first cut.** The §16 starting values are not measured against actual traffic; the auth zone is generous enough to never block a real user, the guest zone may rate-limit aggressive academic crawlers. Recalibration depends on ADR-#10's metrics; a tuning pass after the first month of prod is the expected baseline.
- **Observability is the most-deferred load-bearing concern in this stack.** ADR-#10 inherits a queue depth dashboard need (ADR-0008 §9), several named metrics (ADR-0002 §8, ADR-0007 §4–5, ADR-0008 §4), and the question of log aggregation. The compose graph is structured so that a metrics-emitter sidecar (Prometheus node_exporter + a postgres_exporter, or an OpenTelemetry collector) can be added as a new service without restructuring existing ones.
- **No supply-chain pinning beyond image digests.** Python deps (Poetry lockfile) and Node deps (pnpm lockfile) are pinned in the lockfiles, but `apt-get install` in the backend Dockerfile pulls floating versions of `tesseract-ocr`, `libmagic1`, `poppler-utils`. A Debian-stable base image pins the major versions; minor drift is possible across rebuilds. Flagged; revisit if a tesseract behavior regression ever surfaces.
- **The "one stack, dev = prod" invariant is now load-bearing.** A divergence — say, dev running native uvicorn for speed while prod stays in compose — would erode the topology's main benefit and recreate the macOS/Linux drift this ADR set out to avoid. New contributors get one onboarding doc: `docker compose up -d`.
- **Eight chokepoints (and an honorable mention).** Search (ADR-0001 §9, ADR-0003 §3), embed (ADR-0002 §3), auth (ADR-0005 §3), blob IO (ADR-0006 §3), extraction (ADR-0007 §1), async dispatch (ADR-0008 §3). This ADR adds no new code-level chokepoint but does establish a topology-level one: the deploy script and the compose files are the single answer to "how does this system run?" — and a CI step that diffs `compose.prod.yaml` against `compose.yaml` for service-set parity keeps the two from silently drifting.

## Open dependencies on UNSAM IT

The following are surfaced explicitly so they can be requested as a single coordinated ask rather than discovered piecewise during deploy:

- **DNS A record** for `buscasam.unsam.edu.ar` (or chosen hostname) pointing at the VM.
- **TLS topology confirmation:** does UNSAM terminate TLS upstream of us (we run `TLS_MODE=upstream`) or do we own certs (we run `TLS_MODE=self` + need outbound to Let's Encrypt + inbound on `:80` for HTTP-01 challenge)?
- **Outbound HTTPS** from the VM to `pypi.org`, `registry.npmjs.org`, `ghcr.io`, `github.com` (build-time). Without these, the build-on-VM path (§12) does not work and the deploy mechanism re-opens.
- **One-time outbound** to `huggingface.co` from any workstation that can scp to the VM (for the pre-staging step §10).
- **Backup mount:** off-host storage if available; otherwise we accept same-VM redundancy and the not-DR consequence above.
- **Root or sudo on the VM** for first-time host setup (creating `buscasam:buscasam`, installing Docker, creating `/var/lib/buscasam/` and `/backup/buscasam/`). Not required at deploy time after first setup.
- **Google Cloud OAuth client** scoped to the UNSAM Workspace tenants (already an ADR-0005 dependency; restated here for the IT-coordination single-ask checklist).

If any of these come back as "no" or "yes but not how you expected," the affected §-numbered decision is the one re-opened, not the whole ADR.
