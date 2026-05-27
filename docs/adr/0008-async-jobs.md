# Async job runner: procrastinate, two queues, locked tasks

## Status

Accepted

## Decision

Durable asynchronous work runs on **procrastinate**, backed by the application Postgres database. Two queues partition load: `default` for bounded processing/I/O and `ocr` for CPU-heavy OCR. All async entry points are typed helpers in `core/jobs.py`. Enqueue admission locks reduce duplicate waiting jobs; execution locks and idempotent database transitions provide correctness. Procrastinate periodic defers schedule daily retention/orphan cleanup.

## Locked

1. Runner and transaction integration. Procrastinate uses the same Postgres database as SQLAlchemy; no Redis or RabbitMQ. The backend pins SQLAlchemy async `postgresql+psycopg` and Procrastinate's `PsycopgConnector`. Request-created jobs use `task.configure(connection=<underlying psycopg AsyncConnection>).defer_async(...)` from the active SQLAlchemy transaction, so domain-row creation and job creation commit or roll back together. An integration test proves rollback leaves neither row nor job.

2. Topology: two queues, two worker services in ADR-0009.
   - `default`, concurrency 8 initially: `index_document`, `refresh_headline`, co-author fan-out/send, in-app moderation notification, retention purge, orphan sweep, operator reindex.
   - `ocr`, concurrency 1: `ocr_index_document` only.
   - Initial indexing of every PDF runs the cheap extraction gate on `default`; only a PDF proven to need OCR is delegated to `ocr` under ADR-0007.

3. Chokepoint: task definitions and typed enqueue helpers live in `core/jobs.py`. Feature code imports helpers, not Procrastinate:

   ```python
   async def enqueue_index_document(version_id: int) -> None: ...
   async def enqueue_ocr_index_document(version_id: int) -> None: ...
   async def enqueue_refresh_headline(version_id: int) -> None: ...
   async def enqueue_fan_out_coauthor_invites(document_id: int) -> None: ...
   async def enqueue_send_coauthor_invite(document_id: int, recipient_user_id: int) -> None: ...
   async def enqueue_author_notification(action_id: int) -> None: ...
   async def enqueue_purge_deleted() -> None: ...
   async def enqueue_sweep_orphan_blobs() -> None: ...
   ```

   Architecture tests keep direct task deferral inside `core/jobs.py`/worker wiring. Comment/favourite/history jobs do not exist at MVP.

4. Index pipeline routing:
   - DOCX/ODT: `index_document` completes in `default`.
   - PDF: `index_document` runs `pdfminer` gate in `default`; sufficient-text PDFs complete there.
   - PDF requiring OCR: `index_document` transactionally marks the handoff and enqueues `ocr_index_document`; only `ocr` invokes `ocrmypdf`.
   - Metadata headline edits enqueue `refresh_headline`, which is short and never extracts/OCRs a file.

5. Retry policy:

   | Task | Queue | Max attempts | Backoff | Terminal action |
   |---|---|---:|---|---|
   | `index_document` | `default` | 3 | exponential, base 60 s | candidate `failed` + author notification; current reindex retains old index + operator log |
   | `ocr_index_document` | `ocr` | 3 | exponential, base 60 s | candidate `failed` + author notification; current reindex retains old index + operator log |
   | `refresh_headline` | `default` | 3 | exponential, base 30 s | retain old published headline or block draft publish; notify author |
   | `fan_out_coauthor_invites` | `default` | 3 | exponential, base 60 s | log + notify inviter in-app |
   | `send_coauthor_invite` | `default` | 5 | exponential, base 30 s, cap 1 h | log; invitation remains visible in-app |
   | `author_notification` | `default` | 3 | exponential, base 30 s | log |
   | `purge_deleted`, `sweep_orphan_blobs` | `default` | 3 | exponential, base 5 min | alert in structured logs |

   For candidates, permanent parsing failures abort without retry and set `index_error='corrupted: <short reason>'`; exhausted transient failures set `index_error='exhausted retries: <exception class>'`. Current-version reindex failures keep existing public index rows/status and emit structured operator failure instead of mutating reader-visible state.

   Every fatal indexing path — recognized parse/OCR errors inside `_run_index_document` / `_run_ocr_index_document` *and* exhausted transient failures detected by `_run_attempt` — converges on `core/documents.mark_failed`. `mark_failed` is first-write-wins so the more specific `corrupted:` reason wins over a later `exhausted retries:` reason for the same row. The headline equivalent is `core/documents.mark_headline_refresh_failed`: it leaves `index_status` alone (so the published headline stays current and the draft publish gate keeps blocking on the fingerprint mismatch) and only writes the owner notification.

6. Reindex. Operator CLI `python -m buscasam reindex --reason=embedding|extract` selects published current versions and active unpublished candidates, not historical inactive versions, and enqueues `index_document`. Reindex preserves author-approved published metadata. Published replacements remain current until newly indexed output is explicitly published; administrative full reindex of an unchanged current version swaps index rows only after success.

7. Locks and idempotency:
   - Each helper passes `queueing_lock=<key>` to suppress duplicate waiting jobs, treats `AlreadyEnqueued` as a no-op, and passes `lock=<key>` to prevent simultaneous execution for that logical operation.
   - `queueing_lock` is not treated as an execution guarantee: a job already `doing` does not by itself block a newly queued job.
   - Keys: both initial/OCR indexing use `index:v{id}`; other keys are `headline:v{id}`, `coauthors:d{id}`, `invite:d{id}:u{id}`, `notice:a{id}`, `maintenance:purge`, `maintenance:orphan`.
   - Tasks re-check state under row lock before side effects. Invitation/notification inserts use unique event-recipient keys; indexing writes staged chunks transactionally and fingerprint-checks headline output.

8. Fan-out. A publish action enqueues one `fan_out_coauthor_invites(document_id)` task. It selects pending registered co-authors once and enqueues one `send_coauthor_invite` per recipient. Each send creates the durable in-app invitation and attempts email; duplicate retries cannot create duplicate notification rows.

9. Periodic work. `core/jobs.py` registers daily `purge_deleted` and `sweep_orphan_blobs` periodic tasks on the `default` queue. Any live worker may defer them; Procrastinate records only one defer per period. Reindex remains operator-triggered. Maintenance tasks coordinate with ADR-0009 backups using one Postgres advisory lock namespace so blob deletion cannot race a backup recovery point.

10. Schema management. Procrastinate owns its tables and procedures. Deploy runs `alembic upgrade head && procrastinate schema --apply`, targeting the same DSN. Application migrations do not duplicate Procrastinate DDL.

11. Operator surface. Queue depth, failures, task duration, OCR handoffs, and maintenance failures emit structured stdout logs. Centralized observability/alert delivery is post-MVP.
