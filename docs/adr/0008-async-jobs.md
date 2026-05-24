# Async job runner: procrastinate, two queues, jobs chokepoint

## Status

Accepted

## Decision

Durable async work runs on **procrastinate**, a Postgres-backed task queue using the same database as the primary store. Two queues partition load: `default` (concurrency ~8, I/O-bound) and `ocr` (concurrency 1, CPU-bound). Each queue has its own worker process. All async entry points are typed `enqueue_*` helpers in `core/jobs.py`, CI-grep-enforced. The chokepoint computes a uniform `queueing_lock` per task (silent dedup) and routes `index_document` jobs to `default` or `ocr` via a cheap heuristic (PDF size + MIME) at enqueue time. Procrastinate owns its schema (`procrastinate schema --apply`) inside the same database. No scheduler at MVP — reindex is an operator CLI.

## Locked

1. Runner: procrastinate, same Postgres database as the application. No Redis, no RabbitMQ. Job enqueue inside a request runs through the application's SQLAlchemy connection so the job INSERT and the row INSERT it depends on commit or roll back together. Workers use procrastinate's own asyncpg pool.

2. Topology: two queues, two worker processes.

   - `default` — fast I/O. `worker_default`, concurrency ~8. Hosts: born-digital `index_document`, `fan_out_*` shims, per-recipient SMTP sends, in-app notification inserts, operator-triggered reindex enqueues for born-digital versions.
   - `ocr` — CPU-bound. `worker_ocr`, concurrency 1. Hosts: `index_document` for likely-scans.

   Both built from the same image as the API. Started as separate systemd units (or equivalent — ADR-0009).

3. Chokepoint: typed `enqueue_*` helpers in `core/jobs.py`. All procrastinate task definitions live there. For each task, the module exports a typed helper:

   ```python
   async def enqueue_index_document(version_id: int) -> None: ...
   async def enqueue_fan_out_coauthor_invites(document_id: int) -> None: ...
   async def enqueue_send_coauthor_invite(document_id: int, recipient_user_id: int) -> None: ...
   async def enqueue_fan_out_comment_notifications(comment_id: int) -> None: ...
   async def enqueue_send_comment_notification(comment_id: int, recipient_user_id: int) -> None: ...
   ```

   Feature code only ever imports these helpers; never imports `procrastinate`, never calls `.defer_async(...)` directly. CI grep bans `procrastinate` imports anywhere except `core/jobs.py`, the worker entrypoint, and tests. Helpers use procrastinate's `defer_*` variant accepting an external connection so the application's SQLAlchemy transaction owns the INSERT into `procrastinate_jobs`.

4. Classification heuristic at enqueue time. `enqueue_index_document(version_id)` reads the version's MIME and stored byte size and picks a queue:

   - MIME ∈ {DOCX, ODT MIMEs} → `default`.
   - MIME = `application/pdf`, size ≤ threshold (start at **2 MB**) → `default`.
   - MIME = `application/pdf`, size > threshold → `ocr`.

   Threshold is a tunable in `core/jobs.py`. Metric `ocr_queue_misclassification_rate`. Conservative: when in doubt, route to `ocr`.

5. Retry: two-bucket exception convention + per-task policy.

   - `procrastinate.JobAborted(reason)` → job marked `failed` immediately, no retry. Use for permanent data failures (`PDFSyntaxError`, `zipfile.BadZipFile`, etc.).
   - Any other unhandled exception → procrastinate retries per the task's policy.

   | Task | Queue | Max attempts | Backoff | Terminal action |
   |---|---|---|---|---|
   | `index_document` | `default` / `ocr` | 3 | exponential, base 60 s | `index_status='failed'` + in-app notif (ADR-0007 §9), `index_error` per §9 below |
   | `fan_out_coauthor_invites` | `default` | 3 | exponential, base 60 s | log; in-app notif on inviter |
   | `fan_out_comment_notifications` | `default` | 3 | exponential, base 60 s | log + drop |
   | `send_coauthor_invite` | `default` | 5 | exponential, base 30 s, cap 1 h | log |
   | `send_comment_notification` | `default` | 5 | exponential, base 30 s, cap 1 h | log + drop |

6. Reindex: operator CLI reusing `index_document`. `python -m buscasam reindex --reason=embedding | --reason=extract` selects `document_versions` rows where the relevant version axis is stale and loops `enqueue_index_document(version_id)`. No separate task. Classification (§4) routes per row. Idempotent via §7 lock. No periodic wrapper.

7. Idempotency: uniform `queueing_lock` per helper:

   - `enqueue_index_document(version_id)` → `f"index_document:v{version_id}"`
   - `enqueue_fan_out_coauthor_invites(document_id)` → `f"fan_out_coauthor_invites:d{document_id}"`
   - `enqueue_send_coauthor_invite(document_id, recipient_user_id)` → `f"send_coauthor_invite:d{document_id}:u{recipient_user_id}"`
   - `enqueue_fan_out_comment_notifications(comment_id)` → `f"fan_out_comment_notifications:c{comment_id}"`
   - `enqueue_send_comment_notification(comment_id, recipient_user_id)` → `f"send_comment_notification:c{comment_id}:u{recipient_user_id}"`

   Procrastinate enforces at most one job per lock value across `todo` + `doing`. A duplicate enqueue is a silent no-op.

8. Fan-out: uniform shim. Every fan-out event: the endpoint enqueues one cheap `fan_out_*(event_id)` job; that job resolves recipients via a single SELECT and enqueues one `send_*` per recipient. Shim and per-recipient sends both on `default`. In-app campanita notifications inserted by the per-recipient send job, sharing retry/idempotency primitives with email.

9. Failure surface and `index_error` taxonomy. ADR-0007 §9's `index_status` / `index_error` / `indexed_at` columns are the user-facing surface; `index_error` carries a coarse taxonomy:

   - `corrupted: <short reason>` — set on `JobAborted`. Author notification: "no pudimos procesar el archivo (parece estar dañado)". Offers re-upload.
   - `exhausted retries: <last exception class>` — set when retry policy runs out. Author notification: "no pudimos procesar el archivo (problema temporal del sistema)". Offers retry-from-UI.

   Operator-side observability (queue depth, failure alerts, log aggregation) deferred to ADR-0010. Procrastinate's own tables (`procrastinate_jobs`, `procrastinate_events`) are the source of truth; structured stdout logs from each worker.

10. Schema management. Procrastinate owns its tables (`procrastinate_jobs`, `procrastinate_events`, `procrastinate_periodic_defers`, plus stored procedures and triggers). Deploy runs `alembic upgrade head && procrastinate schema --apply` — both idempotent, both targeting the same DSN. Procrastinate upgrades flow through `pip install procrastinate==X` plus a re-run of the CLI. The application's Alembic history never contains procrastinate DDL.

11. ADR-0003 §4 clarification. The wording "uniform `enqueue(job)` call" is refined to "via the typed `enqueue_*` helpers in `core/jobs.py`." `BackgroundTasks` ban stands unchanged.
