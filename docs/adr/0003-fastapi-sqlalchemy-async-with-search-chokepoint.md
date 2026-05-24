# FastAPI + SQLAlchemy async, with a search-query chokepoint

## Status

Accepted

## Decision

BUSCASAM's backend is a single FastAPI application served by Uvicorn, talking to Postgres through SQLAlchemy 2.0 async with Alembic migrations. The hot search path — RRF fusion, pgvector/`halfvec`, `ltree`, `ts_rank_cd`, and the visibility predicate from ADR-0001 — lives behind one `search_query` module, written as parameterised raw SQL, with a CI grep that blocks those primitives from appearing in any other file. All work that touches an external service (TEI, SMTP, OCR, fan-out) is handed off to the durable queue (ADR-0008) via a uniform `enqueue(job)` call; FastAPI `BackgroundTasks` is banned in code. The API process and the worker process import from the same `core/` package; the queue is the only seam between them.

## Context

ADR-0001 puts hand-written SQL on the request critical path (two CTEs + RRF fusion + ltree filter + visibility/soft-delete predicate). ADR-0002 puts an HTTP call to a TEI sidecar on the same path, with a ~500 ms timeout and a lexical-only fallback. The SPEC's REST/JSON surface covers search, browse, document detail, publishing (with file upload), comments, favourites, notifications, moderation, and an SSO callback — roughly 25–40 endpoints. The team is small and Python-only, on modest UNSAM on-prem hardware. Uploads do not block: the file is persisted, a job is enqueued, the request returns immediately.

## Considered options

- **Django + DRF.** Batteries-included (admin, ORM, migrations, sessions, auth, throttling). Rejected: sync-first. Django async views exist, but the ORM and most third-party packages are sync; on the search path each in-flight TEI roundtrip would pin a worker. The batteries that would justify the cost — admin, ORM, file upload — don't compose with what's already locked: the search query is hand-written SQL the ORM cannot model, the moderation UI is custom anyway (notifications + appeals), and Starlette handles multipart fine.
- **Litestar.** Same async/ASGI/pydantic shape as FastAPI, more opinionated (layered DI without `Depends()` noise, SQLAlchemy repository plugin, DTO system). Rejected at this scope: the structural payoff arrives at 50+ endpoints and 5+ engineers; BUSCASAM is smaller, and the smaller community costs more than the structure saves for a possibly-rotating academic team.
- **SQLAlchemy ORM only (no raw SQL).** Rejected: the RRF query uses pgvector operators, `ltree` `<@`, `ts_rank_cd` over a custom `es_unaccent` config, and partial indexes — primitives the ORM does not model. Forcing it through the ORM would mean fighting it or hiding `text()` blocks anyway.
- **Thin asyncpg / psycopg3 + raw SQL throughout.** Rejected: ~25 endpoints' worth of CRUD (comments, favourites, notifications, user metadata, reports) is real boilerplate the ORM eats. Alembic is too useful to reimplement.
- **FastAPI `BackgroundTasks` for cheap fire-and-forget.** Rejected: tasks die with the worker process (no retry, no visibility) and share the request's event loop (a slow background task delays response completion). Two patterns for "async work" creates ambiguity in a small team. One pattern, one place to look.

## Architecture decisions locked by this ADR

1. **Framework.** FastAPI, pinned to a specific minor in `pyproject.toml`. Uvicorn ASGI server in dev (`--reload`) and prod (multiple workers behind the existing reverse proxy).
2. **Database access.** SQLAlchemy 2.0 async (`AsyncEngine`, `AsyncSession`) + Alembic. Async DB engine created in a FastAPI `lifespan` and injected per-request via a `Depends`-yielded session.
3. **Search-query chokepoint.** One module — `search_query` — owns the RRF SQL builder. Its public surface is `search.run(filters, user_ctx, embedding) -> Results` and `related.run(headline_embedding) -> Results`. The literals `pgvector`, `halfvec`, `ltree`, `<@`, `ts_rank_cd`, `es_unaccent`, and the `WHERE visibility = ...` predicate appear nowhere else in the codebase. A CI grep enforces this. Same shape as ADR-0002 §3.
4. **Always-enqueue rule.** Any code path that touches an external service (TEI for indexing, SMTP, OCR worker), or fans out (notification to N co-authors), goes through `enqueue(job)`. `BackgroundTasks` is banned (CI grep). In-request work is restricted to: pure DB writes the user awaits (comment, favourite, search_history row), reads, and the synchronous search path itself.
5. **Worker / API code sharing.** API and worker processes import from a single `core/` package (models, `search_query`, `embed`, schemas, settings). The queue (ADR-0008) is the only seam; both processes are deployed from the same image / virtualenv and must move together.
6. **DTO discipline.** Pydantic v2 request/response models are separate from SQLAlchemy ORM models. No `response_model=OrmModel`. The wire shape is allowed to diverge from the DB shape (and will: result rows from the search chokepoint are not ORM-mapped).
7. **Configuration.** `pydantic-settings`, env-driven, single `Settings` instance loaded at startup and dependency-injected. The TEI URL, model revision (ADR-0002 §5), DB DSN, and queue DSN are all configured here.
8. **Lifespan-managed clients.** One app-scoped `httpx.AsyncClient` for TEI (reused across requests). One app-scoped `AsyncEngine`. Both created and disposed in the FastAPI `lifespan`. The TEI client lives behind the `embed()` chokepoint from ADR-0002 §3 — feature code never imports `httpx` for TEI calls.
9. **OpenAPI auto-published.** FastAPI's generated schema is the API contract; the frontend (ADR-0004) consumes it. No hand-maintained spec.
10. **Pagination contract.** Offset/limit matching SPEC's `?pagina=N`. Validated by a shared `Pagination` Pydantic model; the search endpoint caps `pagina` at 20 per ADR-0001 §11.

## Consequences

- **Worker contention on the hot path is bounded by I/O, not by the framework.** TEI roundtrip and SQL execution both yield; one worker can hold many in-flight searches. Sizing of Uvicorn worker count is a memory question (DB pool + httpx pool + Python process), not a concurrency question.
- **The chokepoint is load-bearing for correctness, not just style.** A `WHERE` clause in feature code that forgets the visibility filter would leak private documents — the same gravity as ADR-0002's prefix mistake. CI grep is the only thing keeping that out.
- **SQLAlchemy async has gotchas.** Implicit lazy-loading raises at await points; relationships must be eager-loaded (`selectin`) or explicitly awaited. Session-per-request is required (no module-level sessions). These are well-documented but unforgiving — onboarding cost paid once per developer.
- **No Django admin.** Moderation, user management, and reports need their own UI (already implied by SPEC's docente moderation flow, notifications, and appeals). Not a regression — the admin would have wanted heavy customisation anyway.
- **DTO separation adds boilerplate.** ~3× the model count (ORM + Read + Write schemas where they diverge). Pays back when the wire contract is versioned independently of the schema (e.g., renaming a column without breaking clients).
- **One deploy unit, two processes.** API and worker share code, so they must release together — a worker that drifts behind the API may interpret payloads with a stale schema. Acceptable on the single-VM topology (ADR-0009 territory); revisit if processes are ever split across hosts.
- **`BackgroundTasks` ban removes a tempting shortcut.** Sending a single email after a comment requires going through the queue, which feels heavy. The benefit is that "did this email send?" has one answer to look up, and TEI/SMTP outages don't degrade response latency.
- **OpenAPI as contract puts pressure on response models.** Sloppy `dict[str, Any]` responses degrade the spec the frontend depends on. DTO discipline (§6) plus FastAPI's `response_model=` enforces shape at the boundary.
