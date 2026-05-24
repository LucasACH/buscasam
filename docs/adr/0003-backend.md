# FastAPI + SQLAlchemy async, with a search-query chokepoint

## Status

Accepted

## Decision

Single FastAPI app served by Uvicorn, SQLAlchemy 2.0 async with Alembic. Search SQL lives behind `search_query`; all document access policy lives behind `document_access`. Non-search external work (SMTP, OCR/indexing, fan-out) is handed off to the durable queue (ADR-0008) via typed enqueue helpers; synchronous search may call TEI and fall back lexically. FastAPI `BackgroundTasks` is banned. API and worker import from the same `core/` package.

## Locked

1. Framework: FastAPI, pinned to an exact tested version in `pyproject.toml`. Uvicorn ASGI server in dev (`--reload`) and one process in the MVP production container; scale only after VM benchmark.
2. Database access: SQLAlchemy 2.0 async (`AsyncEngine`, `AsyncSession`) + Alembic. Async DB engine created in a FastAPI `lifespan`, injected per-request via a `Depends`-yielded session.
3. Query chokepoints. `core/search_query.py` owns RRF/vector/FTS SQL with surfaces `search.run(filters, user_ctx, embedding: halfvec | None) -> Results` and `related.run(doc_id, user_ctx) -> Results`; `embedding=None` means lexical fallback and related retrieves the source vector only through readable access. `core/document_access.py` owns ADR-0010 access fragments and surfaces for readable detail/download/sitemap and moderation reads. Unit/endpoint tests verify no document-returning route bypasses access; migrations may contain schema/index literals.
4. Always-enqueue rule. Any non-search code path that touches an external service (TEI for indexing, SMTP, OCR) or fans out (notification to co-authors) uses the typed `enqueue_*` helpers from ADR-0008. `BackgroundTasks` is banned. In-request work is restricted to reads, awaited DB writes, auth redirect/exchange, streamed blob ingest, and synchronous search's bounded TEI call.
5. Worker/API code sharing. Both processes import from a single `core/` package (models, `search_query`, `embed`, schemas, settings). The queue is the only seam; both deployed from the same image and must move together.
6. DTO discipline. Pydantic v2 request/response models separate from SQLAlchemy ORM. No `response_model=OrmModel`. Search result rows are not ORM-mapped.
7. Configuration: `pydantic-settings`, env-driven, single `Settings` instance loaded at startup and dependency-injected. The async SQLAlchemy driver is `postgresql+psycopg`, required for transactional Procrastinate enqueue integration in ADR-0008.
8. Lifespan-managed clients. One app-scoped `httpx.AsyncClient` for TEI. One app-scoped `AsyncEngine`. Both created and disposed in the FastAPI `lifespan`. The TEI client lives behind the `embed()` chokepoint (ADR-0002 §3) — feature code never imports `httpx` for TEI calls.
9. OpenAPI auto-published. FastAPI's generated schema is the API contract; the frontend (ADR-0004) consumes it. No hand-maintained spec.
10. Pagination contract: offset/limit matching SPEC's `?pagina=N`. Validated by a shared `Pagination` Pydantic model; relevance search caps `pagina` at 20 (ADR-0001).
11. MVP routes implement ADR-0010 only: auth/me; draft/upload/metadata/publish/co-author actions; notifications list/ack; search/detail/related/download; document report/moderation. Deferred social/personalization endpoints are absent.
