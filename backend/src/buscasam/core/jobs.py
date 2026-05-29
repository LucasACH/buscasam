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
from buscasam.core import notifications
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


# --- Plain async cores (callable by tests + by the task body wrapper). ---


async def _complete_indexing(
    sm,
    tei: httpx.AsyncClient,
    cv: documents.CandidateVersion,
    doc: extractmod.ExtractedDoc,
) -> None:
    """Embed the candidate's text (no row lock held) and persist it through the
    finalize transaction (ADR-0011 §5). `write_indexed_candidate` is gated on
    `index_status='processing'`, so a descartar committed during the embed IO
    makes this write a clean no-op — no chunks materialize on a discarded row."""
    meta = extractmod.derive_metadata(doc)
    body = chunkmod.chunk(doc)
    headline = chunkmod.headline_chunk(cv.title, meta.abstract)
    fp = chunkmod.headline_fingerprint(cv.title, meta.abstract)

    texts = [c.body_text for c in [headline, *body]]
    embeds = [await embedmod.embed(tei, t, kind="passage") for t in texts]

    async with sm() as session:
        await documents.write_indexed_candidate(
            session,
            cv.version_id,
            body=body,
            headline=headline,
            embeds=embeds,
            meta=meta,
            headline_fingerprint=fp,
        )
        await session.commit()


async def _claim(sm, version_id: int) -> documents.CandidateVersion | None:
    """Short claim transaction: move pending→processing and commit, releasing
    `_begin_indexing`'s FOR UPDATE before the extract/OCR/embed IO (ADR-0011 §5,
    ADR-0008 §3). Returns the candidate, or None when the row is already
    'indexed' (retry no-op) or 'discarded' (descartado, abort). 'processing' is
    re-enterable: a prior attempt whose IO failed left it there, and the claim
    re-claims it on retry."""
    async with sm() as session:
        cv = await documents._begin_indexing(session, version_id)
        await session.commit()
    return cv


async def _run_index_document(sm, tei: httpx.AsyncClient, version_id: int) -> None:
    cv = await _claim(sm, version_id)
    if cv is None:
        return
    # The row lock is released by _claim's commit, so extract/embed run lock-free
    # and a concurrent descartar can commit while this IO is in flight; the
    # guarded finalize write aborts atomically against a discarded row.
    try:
        doc = await extractmod.extract(cv.sha256, cv.mime)
    except extractmod.OCRRequired:
        async with sm() as session:
            await enqueue_ocr_index_document(session, version_id)
            await session.commit()
        return
    except (PDFSyntaxError, zipfile.BadZipFile) as e:
        async with sm() as session:
            await documents.mark_failed(
                session, version_id, error=f"corrupted: {type(e).__name__}"
            )
            await session.commit()
        return

    await _complete_indexing(sm, tei, cv, doc)


async def _run_ocr_index_document(
    sm, tei: httpx.AsyncClient, version_id: int
) -> None:
    """Runs ocrmypdf to add a text layer, then re-extracts from the OCR'd bytes.

    The claim commits 'processing' and releases the row lock *before* the
    ~30-min OCR run (ADR-0011 §5), so a descartar no longer blocks behind the
    OCR IO window — the finalize write is what aborts atomically against a
    discarded row."""
    cv = await _claim(sm, version_id)
    if cv is None:
        return
    try:
        import ocrmypdf
        from ocrmypdf.exceptions import ExitCodeException
    except ImportError as e:
        async with sm() as session:
            await documents.mark_failed(
                session, version_id, error=f"ocr_unavailable: {type(e).__name__}"
            )
            await session.commit()
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
        async with sm() as session:
            await documents.mark_failed(
                session, version_id, error=f"ocr_failed: {type(e).__name__}"
            )
            await session.commit()
        return

    # ADR-0007 §10: the OCR'd PDF is a scratch artifact — it goes through
    # blob_store (architecture rule) but must not survive the task.
    async def _one_chunk():
        yield out_buf.getvalue()

    put = await blob_store.put_stream(_one_chunk(), max_bytes=200_000_000)
    try:
        doc = await extractmod.extract(put.sha256, "application/pdf")
        await _complete_indexing(sm, tei, cv, doc)
    finally:
        async with sm() as session:
            await blob_store.discard_if_unreferenced(session, put.sha256)
            await session.commit()


async def _run_refresh_headline(
    sm, tei: httpx.AsyncClient, version_id: int
) -> None:
    async with sm() as session:
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
    async with sm() as session:
        await documents.write_headline(session, version_id, headline, embed, fp)
        await session.commit()


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
        await notifications.notify_coauthor_invite(
            session,
            user_id=r["user_id"],
            doc_id=doc_id,
            doc_title=r["doc_title"],
            inviter=r["inviter"],
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
    the predicate). Returns the rowcount the worker logs for operators."""
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
    errors. Returns the candidate count the worker logs for operators."""
    count = 0
    async for sha in blob_store.iter_orphan_candidates(min_age=_BLOB_GRACE):
        await blob_store.discard_if_unreferenced(session, sha)
        count += 1
    return count


# --- Procrastinate task bodies (production worker entry points). ---
#
# Each body resolves a per-job sessionmaker + TEI client. The _run_* cores own
# their transactions — a short claim tx, the lock-free extract/OCR/embed IO, and
# a guarded finalize tx (ADR-0011 §5) — so _run_attempt only adds the
# retry→terminal handling. Tests drive the _run_* cores directly so the worker
# wiring stays untested-but-thin.


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

    The runner owns its own claim/finalize transactions; this wrapper only
    handles failure. On uncaught failure it asks the task's retry strategy
    whether another attempt remains, and if not opens a fresh session to call
    `on_terminal` — so every fatal path (recognized parse/OCR errors inside the
    runner *and* exhausted transient failures here) converges on
    `documents.mark_failed` / `documents.mark_headline_refresh_failed`. The
    candidate row is left in 'processing' by the claim commit; a retried attempt
    re-claims it, and `on_terminal` flips 'processing'→'failed' under its guard.
    """
    sm, tei = _get_worker_resources()
    try:
        await runner(sm, tei, version_id)
        return
    except Exception as exc:
        will_retry = (
            context.task.get_retry_exception(exception=exc, job=context.job)
            is not None
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
        raise


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


async def _run_maintenance(name: str, runner) -> None:
    """Shared body for the periodic maintenance tasks: open a worker session,
    take the maintenance advisory lock, run the core, commit, and log the count
    (these jobs are silent to authors but observable to operators). The advisory
    lock releases with the transaction (ADR-0008 §9)."""
    sm, _ = _get_worker_resources()
    async with sm() as session:
        try:
            async with _with_maintenance_lock(session):
                count = await runner(session)
            await session.commit()
            logger.info("maintenance %s count=%s", name, count)
        except Exception:
            await session.rollback()
            raise


@app.periodic(cron=_PURGE_CRON)
@app.task(queue="default", retry=_MAINT_RETRY)
async def purge_deleted(timestamp: int) -> None:
    await _run_maintenance("purge_deleted", _run_purge_deleted)


@app.periodic(cron=_SWEEP_CRON)
@app.task(queue="default", retry=_MAINT_RETRY)
async def sweep_orphan_blobs(timestamp: int) -> None:
    await _run_maintenance("sweep_orphan_blobs", _run_sweep_orphan_blobs)


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
