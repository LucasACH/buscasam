# FastAPI + SQLAlchemy async, with a search-query chokepoint

## Status

Accepted

## Decision

Single FastAPI app served by Uvicorn, SQLAlchemy 2.0 async with Alembic. The hot search path lives behind one `search_query` module as parameterised raw SQL, CI-grep-enforced. All work touching an external service (TEI, SMTP, OCR, fan-out) is handed off to the durable queue (ADR-0008) via `enqueue(job)`; FastAPI `BackgroundTasks` is banned. API and worker import from the same `core/` package; the queue is the only seam.

## Locked

1. Framework: FastAPI, pinned to a specific minor in `pyproject.toml`. Uvicorn ASGI server in dev (`--reload`) and prod (multiple workers behind the reverse proxy).
2. Database access: SQLAlchemy 2.0 async (`AsyncEngine`, `AsyncSession`) + Alembic. Async DB engine created in a FastAPI `lifespan`, injected per-request via a `Depends`-yielded session.
3. Search-query chokepoint. One module — `search_query` — owns the RRF SQL builder. Public surface: `search.run(filters, user_ctx, embedding) -> Results` and `related.run(headline_embedding) -> Results`. Literals `pgvector`, `halfvec`, `ltree`, `<@`, `ts_rank_cd`, `es_unaccent`, and the `WHERE visibility = ...` predicate appear nowhere else. CI grep enforces.
4. Always-enqueue rule. Any code path that touches an external service (TEI for indexing, SMTP, OCR worker) or fans out (notification to N co-authors) goes through `enqueue(job)`. `BackgroundTasks` is banned (CI grep). In-request work is restricted to: pure DB writes the user awaits (comment, favourite, search_history row), reads, and the synchronous search path itself.
5. Worker/API code sharing. Both processes import from a single `core/` package (models, `search_query`, `embed`, schemas, settings). The queue is the only seam; both deployed from the same image and must move together.
6. DTO discipline. Pydantic v2 request/response models separate from SQLAlchemy ORM. No `response_model=OrmModel`. Search result rows are not ORM-mapped.
7. Configuration: `pydantic-settings`, env-driven, single `Settings` instance loaded at startup and dependency-injected.
8. Lifespan-managed clients. One app-scoped `httpx.AsyncClient` for TEI. One app-scoped `AsyncEngine`. Both created and disposed in the FastAPI `lifespan`. The TEI client lives behind the `embed()` chokepoint (ADR-0002 §3) — feature code never imports `httpx` for TEI calls.
9. OpenAPI auto-published. FastAPI's generated schema is the API contract; the frontend (ADR-0004) consumes it. No hand-maintained spec.
10. Pagination contract: offset/limit matching SPEC's `?pagina=N`. Validated by a shared `Pagination` Pydantic model; the search endpoint caps `pagina` at 20 (ADR-0001 §11).
