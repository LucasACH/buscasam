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

import httpx
from pdfminer.pdfparser import PDFSyntaxError
from procrastinate import App, PsycopgConnector, RetryStrategy
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


def _index_lock(version_id: int) -> str:
    return f"index:v{version_id}"


def _headline_lock(version_id: int) -> str:
    return f"headline:v{version_id}"


# --- Plain async cores (callable by tests + by the task body wrapper). ---


async def _run_index_document(
    session: AsyncSession, tei: httpx.AsyncClient, version_id: int
) -> None:
    cv = await documents.load_candidate(session, version_id)
    await session.execute(
        text("UPDATE document_versions SET index_status = 'processing' WHERE id = :id"),
        {"id": version_id},
    )
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

    meta = extractmod.derive_metadata(doc)
    body = chunkmod.chunk(doc)
    headline = chunkmod.headline_chunk(cv.title, meta.abstract)
    fp = chunkmod.headline_fingerprint(cv.title, meta.abstract)

    texts = [c.body_text for c in [headline, *body]]
    embeds = [await embedmod.embed(tei, t, kind="passage") for t in texts]

    await documents.write_indexed_candidate(
        session,
        version_id,
        body=body,
        headline=headline,
        embeds=embeds,
        meta=meta,
        headline_fingerprint=fp,
    )


async def _run_ocr_index_document(
    session: AsyncSession, tei: httpx.AsyncClient, version_id: int
) -> None:
    """Runs ocrmypdf to add a text layer, then re-extracts from the OCR'd bytes."""
    cv = await documents.load_candidate(session, version_id)
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
        meta = extractmod.derive_metadata(doc)
        body = chunkmod.chunk(doc)
        headline = chunkmod.headline_chunk(cv.title, meta.abstract)
        fp = chunkmod.headline_fingerprint(cv.title, meta.abstract)
        texts = [c.body_text for c in [headline, *body]]
        embeds = [await embedmod.embed(tei, t, kind="passage") for t in texts]
        await documents.write_indexed_candidate(
            session,
            version_id,
            body=body,
            headline=headline,
            embeds=embeds,
            meta=meta,
            headline_fingerprint=fp,
        )
    finally:
        await blob_store.delete(put.sha256)


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


async def _run_with_session(runner, version_id: int) -> None:
    sm, tei = _get_worker_resources()
    async with sm() as session:
        try:
            await runner(session, tei, version_id)
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@app.task(queue="default", retry=_DEFAULT_RETRY)
async def index_document(version_id: int) -> None:
    await _run_with_session(_run_index_document, version_id)


@app.task(queue="ocr", retry=_DEFAULT_RETRY)
async def ocr_index_document(version_id: int) -> None:
    await _run_with_session(_run_ocr_index_document, version_id)


@app.task(queue="default", retry=_HEADLINE_RETRY)
async def refresh_headline(version_id: int) -> None:
    await _run_with_session(_run_refresh_headline, version_id)


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


async def enqueue_fan_out_coauthor_invites(
    session: AsyncSession, doc_id: int
) -> None:
    """No-op stub at this PRD's window (ADR-0008 §3, module map §core/jobs).

    `core/documents.publish` calls this to fan out invites for any `pending`
    coauthor rows. PRD #5 fills the task body and the send; until then publish
    must still call it so the seam exists.
    """
    return
