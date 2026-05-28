"""Async job runner (ADR-0008, module map §core/jobs).

Single concentration point for "what async work exists and how it retries".
Feature code imports the typed enqueue helpers — never `procrastinate`
directly (ADR-0008 §3, architecture test in tests/unit/test_jobs_architecture.py).
"""
from __future__ import annotations

import asyncio
import io
import logging
import zipfile
from contextlib import asynccontextmanager
from datetime import timedelta

import httpx
from pdfminer.pdfparser import PDFSyntaxError
from procrastinate import App, JobContext, PsycopgConnector, RetryStrategy
from procrastinate.exceptions import AlreadyEnqueued
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from buscasam.core import blob_store
from buscasam.core import chunk as chunkmod
from buscasam.core import documents
from buscasam.core import embed as embedmod
from buscasam.core import extract as extractmod
from buscasam.settings import settings

logger = logging.getLogger(__name__)


def _make_app() -> App:
    url = settings.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    return App(connector=PsycopgConnector(conninfo=url))


app = _make_app()


# ADR-0008 §5: max 3 attempts; index/ocr base 60s, headline base 30s; exponential.
_DEFAULT_RETRY = RetryStrategy(max_attempts=3, wait=60, exponential_wait=True)
_HEADLINE_RETRY = RetryStrategy(max_attempts=3, wait=30, exponential_wait=True)
# ADR-0008 §5: maintenance jobs retry 3× with exponential backoff, base 5 min.
_MAINT_RETRY = RetryStrategy(max_attempts=3, wait=300, exponential_wait=True)

# Daily, off-peak. Any live worker may defer; Procrastinate records one defer
# per period (ADR-0008 §9).
_PURGE_CRON = "0 3 * * *"
_SWEEP_CRON = "30 3 * * *"

# Single Postgres advisory-lock namespace shared with ADR-0009 backups, so blob
# deletion cannot race a backup recovery point (ADR-0008 §9, ADR-0006 §13). Any
# new maintenance/backup job that touches blobs must take this same key.
_MAINTENANCE_LOCK_KEY = 0x6273_6D6E  # "bsmn"


def _index_lock(version_id: int) -> str:
    return f"index:v{version_id}"


def _headline_lock(version_id: int) -> str:
    return f"headline:v{version_id}"


def _coauthor_lock(doc_id: int) -> str:
    return f"coauthors:d{doc_id}"


def coauthor_invite_event_key(doc_id: int, user_id: int) -> str:
    """Dedup key for coauthor-invite notifications (module map §core/jobs,
    ADR-0010 §9). The single producer/consumer format: the fan-out inserts
    under it; core/documents.accept_invitation/decline_invitation mark it read."""
    return f"coauthor_invite:{doc_id}:{user_id}"


# --- Plain async cores (callable by tests + by the task body wrapper). ---


async def _complete_indexing(
    session: AsyncSession,
    tei: httpx.AsyncClient,
    cv: documents.CandidateVersion,
    doc: extractmod.ExtractedDoc,
) -> None:
    meta = extractmod.derive_metadata(doc)
    body = chunkmod.chunk(doc)
    headline = chunkmod.headline_chunk(cv.title, meta.abstract)
    fp = chunkmod.headline_fingerprint(cv.title, meta.abstract)

    texts = [c.body_text for c in [headline, *body]]
    embeds = [await embedmod.embed(tei, t, kind="passage") for t in texts]

    await documents.write_indexed_candidate(
        session,
        cv.version_id,
        body=body,
        headline=headline,
        embeds=embeds,
        meta=meta,
        headline_fingerprint=fp,
    )


async def _run_index_document(
    session: AsyncSession, tei: httpx.AsyncClient, version_id: int
) -> None:
    cv = await documents._begin_indexing(session, version_id)
    if cv is None:
        return
    try:
        doc = await extractmod.extract(cv.sha256, cv.mime)
    except extractmod.OCRRequired:
        await enqueue_ocr_index_document(session, version_id)
        return
    except (PDFSyntaxError, zipfile.BadZipFile) as e:
        await documents.mark_failed(
            session, version_id, error=f"corrupted: {type(e).__name__}"
        )
        return

    await _complete_indexing(session, tei, cv, doc)


async def _run_ocr_index_document(
    session: AsyncSession, tei: httpx.AsyncClient, version_id: int
) -> None:
    """Runs ocrmypdf to add a text layer, then re-extracts from the OCR'd bytes."""
    cv = await documents._begin_indexing(session, version_id)
    if cv is None:
        return
    try:
        import ocrmypdf
        from ocrmypdf.exceptions import ExitCodeException
    except ImportError as e:
        await documents.mark_failed(
            session, version_id, error=f"ocr_unavailable: {type(e).__name__}"
        )
        return

    raw_pdf = bytearray()
    async for chunk in blob_store.open_for_send(cv.sha256):
        raw_pdf.extend(chunk)

    out_buf = io.BytesIO()
    try:
        # ADR-0008 §11: OCR can take ~30 min on CPU. Run in a worker thread so
        # the event loop stays responsive (heartbeats, signals, cancellation).
        await asyncio.to_thread(
            ocrmypdf.ocr,
            io.BytesIO(bytes(raw_pdf)),
            out_buf,
            language=["spa", "eng"],
            skip_text=True,
            progress_bar=False,
        )
    except ExitCodeException as e:
        # ocrmypdf documented input/config failure → terminal for this candidate.
        logger.warning("ocr_failed version_id=%s", version_id, exc_info=True)
        await documents.mark_failed(
            session, version_id, error=f"ocr_failed: {type(e).__name__}"
        )
        return

    # ADR-0007 §10: the OCR'd PDF is a scratch artifact — it goes through
    # blob_store (architecture rule) but must not survive the task.
    async def _one_chunk():
        yield out_buf.getvalue()

    put = await blob_store.put_stream(_one_chunk(), max_bytes=200_000_000)
    try:
        doc = await extractmod.extract(put.sha256, "application/pdf")
        await _complete_indexing(session, tei, cv, doc)
    finally:
        await blob_store.discard_if_unreferenced(session, put.sha256)


async def _run_refresh_headline(
    session: AsyncSession, tei: httpx.AsyncClient, version_id: int
) -> None:
    cv = await documents.load_candidate(session, version_id)
    staged_abstract = (
        await session.execute(
            text("SELECT staged_abstract FROM document_versions WHERE id = :id"),
            {"id": version_id},
        )
    ).scalar_one() or ""
    headline = chunkmod.headline_chunk(cv.title, staged_abstract)
    fp = chunkmod.headline_fingerprint(cv.title, staged_abstract)
    embed = await embedmod.embed(tei, headline.body_text, kind="passage")
    await documents.write_headline(session, version_id, headline, embed, fp)


async def _run_fan_out_coauthor_invites(session: AsyncSession, doc_id: int) -> None:
    """Insert one coauthor_invite notification per pending registered coautor,
    deduped on (user_id, event_key). Re-runnable: ON CONFLICT DO NOTHING is the
    only idempotency mechanism, so retries after partial completion add zero
    duplicates (module map §core/jobs, PRD story 27)."""
    rows = (
        await session.execute(
            text(
                "SELECT da.user_id AS user_id, d.titulo AS doc_title, "
                "       o.display_name AS inviter "
                "FROM document_authors da "
                "JOIN documents d ON d.id = da.doc_id "
                "LEFT JOIN document_authors o "
                "  ON o.doc_id = da.doc_id AND o.status = 'owner' "
                "WHERE da.doc_id = :doc_id AND da.status = 'pending' "
                "  AND da.user_id IS NOT NULL"
            ),
            {"doc_id": doc_id},
        )
    ).mappings().all()
    for r in rows:
        await session.execute(
            text(
                "INSERT INTO notifications (user_id, event_key, kind, payload_json) "
                "VALUES (:uid, :ek, 'coauthor_invite', "
                "        jsonb_build_object('doc_title', cast(:doc_title as text), "
                "                           'doc_id', cast(:doc_id as bigint), "
                "                           'inviter', cast(:inviter as text))) "
                "ON CONFLICT (user_id, event_key) DO NOTHING"
            ),
            {
                "uid": r["user_id"],
                "ek": coauthor_invite_event_key(doc_id, r["user_id"]),
                "doc_title": r["doc_title"],
                "doc_id": doc_id,
                "inviter": r["inviter"],
            },
        )


@asynccontextmanager
async def _with_maintenance_lock(session: AsyncSession):
    """Serialize blob-touching maintenance against ADR-0009 backup recovery
    points via the shared advisory-lock namespace (ADR-0008 §9). The lock is
    transaction-scoped, so it auto-releases when the body commits or rolls
    back — no explicit unlink path to leak."""
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:k)"), {"k": _MAINTENANCE_LOCK_KEY}
    )
    yield


async def _run_purge_deleted(session: AsyncSession) -> int:
    """Hard-delete documents whose 180-día retention window has elapsed
    (ADR-0006 §12, module map §core/jobs). `ON DELETE CASCADE` collects
    versions, attachments, and chunks. In-window and never-deleted documents
    are untouched; idempotent (a retried run deletes only rows still matching
    the predicate). Returns the rowcount for the structured operator log."""
    result = await session.execute(
        text(
            "DELETE FROM documents "
            "WHERE soft_deleted_at < now() - INTERVAL '180 days'"
        )
    )
    return result.rowcount


# ADR-0006 §12: skip blobs whose final-path mtime is younger than this grace,
# so an in-flight upload (renamed into place but not yet committed to a row)
# is never reclaimed.
_BLOB_GRACE = timedelta(hours=24)


async def _run_sweep_orphan_blobs(session: AsyncSession) -> int:
    """Reclaim past-grace blobs no live row references (ADR-0006 §12, module
    map §core/jobs). Drives `blob_store.iter_orphan_candidates` into the
    existing per-sha `discard_if_unreferenced`, which skips a still-referenced
    sha and unlinks missing_ok — so a retried run neither double-deletes nor
    errors. Returns the candidate count for the structured operator log."""
    count = 0
    async for sha in blob_store.iter_orphan_candidates(min_age=_BLOB_GRACE):
        await blob_store.discard_if_unreferenced(session, sha)
        count += 1
    return count


# --- Procrastinate task bodies (production worker entry points). ---
#
# Each body opens its own SQLAlchemy session + TEI client per job. Tests drive
# the _run_* cores directly so the worker wiring stays untested-but-thin.


_worker_engine: object | None = None
_worker_sessionmaker: object | None = None
_worker_tei: httpx.AsyncClient | None = None


def _get_worker_resources():
    global _worker_engine, _worker_sessionmaker, _worker_tei
    if _worker_sessionmaker is None:
        _worker_engine = create_async_engine(settings.database_url)
        _worker_sessionmaker = async_sessionmaker(_worker_engine, expire_on_commit=False)
    if _worker_tei is None:
        _worker_tei = httpx.AsyncClient(base_url=settings.tei_url)
    return _worker_sessionmaker, _worker_tei


async def _terminal_index_failure(
    session: AsyncSession, version_id: int, exc: BaseException
) -> None:
    await documents.mark_failed(
        session, version_id, error=f"exhausted retries: {type(exc).__name__}"
    )


async def _terminal_headline_failure(
    session: AsyncSession, version_id: int, exc: BaseException
) -> None:
    await documents.mark_headline_refresh_failed(
        session, version_id, reason=f"exhausted retries: {type(exc).__name__}"
    )


async def _run_attempt(context, runner, version_id, on_terminal) -> None:
    """Single chokepoint for indexing terminal outcomes (ADR-0008 §5).

    Runs `runner` in a worker session. On uncaught failure: rolls back, asks
    the task's retry strategy whether another attempt remains, and if not,
    opens a fresh session to call `on_terminal` — so every fatal path
    (recognized parse/OCR errors inside the runner *and* exhausted transient
    failures here) converges on `documents.mark_failed` /
    `documents.mark_headline_refresh_failed`.
    """
    sm, tei = _get_worker_resources()
    exc: BaseException | None = None
    async with sm() as session:
        try:
            await runner(session, tei, version_id)
            await session.commit()
            return
        except Exception as e:
            await session.rollback()
            exc = e

    will_retry = (
        context.task.get_retry_exception(exception=exc, job=context.job) is not None
    )
    if not will_retry:
        async with sm() as terminal_session:
            try:
                await on_terminal(terminal_session, version_id, exc)
                await terminal_session.commit()
            except Exception:
                await terminal_session.rollback()
                logger.exception(
                    "terminal_handler_failed version_id=%s task=%s",
                    version_id,
                    context.job.task_name,
                )
    raise exc


@app.task(queue="default", retry=_DEFAULT_RETRY, pass_context=True)
async def index_document(context: JobContext, version_id: int) -> None:
    await _run_attempt(
        context, _run_index_document, version_id, _terminal_index_failure
    )


@app.task(queue="ocr", retry=_DEFAULT_RETRY, pass_context=True)
async def ocr_index_document(context: JobContext, version_id: int) -> None:
    await _run_attempt(
        context, _run_ocr_index_document, version_id, _terminal_index_failure
    )


@app.task(queue="default", retry=_HEADLINE_RETRY, pass_context=True)
async def refresh_headline(context: JobContext, version_id: int) -> None:
    await _run_attempt(
        context, _run_refresh_headline, version_id, _terminal_headline_failure
    )


async def _run_maintenance(runner) -> None:
    """Shared body for the periodic maintenance tasks: open a worker session,
    take the maintenance advisory lock, run the core, commit. The advisory lock
    releases with the transaction (ADR-0008 §9)."""
    sm, _ = _get_worker_resources()
    async with sm() as session:
        try:
            async with _with_maintenance_lock(session):
                await runner(session)
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@app.periodic(cron=_PURGE_CRON)
@app.task(queue="default", retry=_MAINT_RETRY)
async def purge_deleted(timestamp: int) -> None:
    await _run_maintenance(_run_purge_deleted)


@app.periodic(cron=_SWEEP_CRON)
@app.task(queue="default", retry=_MAINT_RETRY)
async def sweep_orphan_blobs(timestamp: int) -> None:
    await _run_maintenance(_run_sweep_orphan_blobs)


@app.task(queue="default", retry=_DEFAULT_RETRY)
async def fan_out_coauthor_invites(doc_id: int) -> None:
    sm, _ = _get_worker_resources()
    async with sm() as session:
        try:
            await _run_fan_out_coauthor_invites(session, doc_id)
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# --- Typed enqueue helpers (ADR-0008 §3, transactional defer §1). ---


async def _raw_psycopg_conn(session: AsyncSession):
    """Reach through SQLAlchemy to the underlying psycopg AsyncConnection.

    ADR-0008 §1: deferring through the active transaction's connection means
    the domain row and the job INSERT commit (or roll back) together.
    """
    sa_conn = await session.connection()
    raw = await sa_conn.get_raw_connection()
    return raw.driver_connection


async def _defer_with_savepoint(task, *, lock: str, **defer_kwargs) -> None:
    """Wrap procrastinate's defer in a SAVEPOINT so an AlreadyEnqueued duplicate
    does not abort the outer SQLAlchemy transaction (ADR-0008 §7).

    The SAVEPOINT is issued through the raw psycopg cursor — not via
    `session.begin_nested()` — because procrastinate's defer_async writes
    directly on the underlying psycopg connection. SQLAlchemy's savepoint
    layer cannot recover the connection's `InFailedSqlTransaction` state on
    a procrastinate UniqueViolation; a cursor-level ROLLBACK TO SAVEPOINT can.
    """
    session: AsyncSession = defer_kwargs.pop("session")
    conn = await _raw_psycopg_conn(session)
    savepoint = f"sp_enqueue_{lock.replace(':', '_')}"
    async with conn.cursor() as cur:
        await cur.execute(f"SAVEPOINT {savepoint}")
    try:
        await task.configure(
            queueing_lock=lock, lock=lock, connection=conn,
        ).defer_async(**defer_kwargs)
    except AlreadyEnqueued:
        async with conn.cursor() as cur:
            await cur.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
        return
    async with conn.cursor() as cur:
        await cur.execute(f"RELEASE SAVEPOINT {savepoint}")


async def enqueue_index_document(session: AsyncSession, version_id: int) -> None:
    await _defer_with_savepoint(
        index_document,
        lock=_index_lock(version_id),
        session=session,
        version_id=version_id,
    )


async def enqueue_ocr_index_document(
    session: AsyncSession, version_id: int
) -> None:
    """Same lock key as index_document per ADR-0008 §7 (`index:v{id}`)."""
    await _defer_with_savepoint(
        ocr_index_document,
        lock=_index_lock(version_id),
        session=session,
        version_id=version_id,
    )


async def enqueue_refresh_headline(session: AsyncSession, version_id: int) -> None:
    await _defer_with_savepoint(
        refresh_headline,
        lock=_headline_lock(version_id),
        session=session,
        version_id=version_id,
    )


async def enqueue_purge_deleted(session: AsyncSession) -> None:
    """Lock `maintenance:purge` (ADR-0008 §7); AlreadyEnqueued → no-op.
    `timestamp=0` is the periodic-task arg supplied for a manual defer (the
    periodic deferrer passes the period timestamp; the body ignores it)."""
    await _defer_with_savepoint(
        purge_deleted, lock="maintenance:purge", session=session, timestamp=0
    )


async def enqueue_sweep_orphan_blobs(session: AsyncSession) -> None:
    """Lock `maintenance:orphan` (ADR-0008 §7); AlreadyEnqueued → no-op.
    `timestamp=0` mirrors `enqueue_purge_deleted` (periodic-task arg)."""
    await _defer_with_savepoint(
        sweep_orphan_blobs, lock="maintenance:orphan", session=session, timestamp=0
    )


async def enqueue_fan_out_coauthor_invites(
    session: AsyncSession, doc_id: int
) -> None:
    """Defer the publish-time / post-publish coauthor fan-out (module map
    §core/jobs). Lock `coauthors:d{doc_id}` (ADR-0008 §7) collapses a duplicate
    enqueue to a no-op."""
    await _defer_with_savepoint(
        fan_out_coauthor_invites,
        lock=_coauthor_lock(doc_id),
        session=session,
        doc_id=doc_id,
    )
