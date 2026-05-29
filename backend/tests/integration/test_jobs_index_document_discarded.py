"""The worker discarded-gate (issue #59, module map §core/jobs + §core/documents,
ADR-0011 §5). A descartar committed against a candidate is terminal: the worker
write functions match zero rows and never resurrect the row or materialize chunks.

Most cases are driven directly against the session fixture — no worker, no lock
contention; the race is modeled linearly (begin → discard → worker write) to
exercise the gate's `WHERE index_status='processing'` predicate in isolation.
`test_descartar_completes_while_indexing_io_in_flight` adds the real
two-connection proof that the new claim/finalize lifecycle releases the row lock
before the extract IO, so descartar no longer blocks behind it."""
from __future__ import annotations

import asyncio

import httpx
import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from buscasam.core import documents, jobs
from buscasam.core.auth import UserCtx
from buscasam.core.chunk import Chunk, headline_chunk, headline_fingerprint
from buscasam.core.extract import ExtractedDoc, IndexableMetadata
from tests.factories import make_document, make_document_author, make_user


def _tei_mock() -> httpx.AsyncClient:
    def handler(req: httpx.Request) -> httpx.Response:
        import json

        n = len(json.loads(req.read())["inputs"])
        return httpx.Response(200, json=[[0.1] * 1024] * n)

    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://tei"
    )


def _ctx(user_id: int) -> UserCtx:
    return UserCtx(user_id=user_id, is_unsam=True, role="estudiante")


async def _seed_published_with_candidate(
    session, *, owner_user_id: int, candidate_status: str = "pending"
) -> tuple[int, int]:
    """Published doc + one non-current candidate. Returns (doc_id, candidate_vid)."""
    doc_id = await make_document(session, publication_status="published", titulo="Tesis")
    await make_document_author(session, doc_id, user_id=owner_user_id, status="owner")
    await session.execute(
        text(
            "INSERT INTO document_versions "
            "(doc_id, version_no, sha256, original_filename, bytes, mime, "
            " uploaded_by, index_status, is_current, first_published_at) "
            "VALUES (:d, 1, decode('aa', 'hex'), 'original.pdf', 2048, "
            " 'application/pdf', :uid, 'indexed', true, now())"
        ),
        {"d": doc_id, "uid": owner_user_id},
    )
    candidate_vid = (
        await session.execute(
            text(
                "INSERT INTO document_versions "
                "(doc_id, version_no, sha256, original_filename, bytes, mime, "
                " uploaded_by, index_status, is_current) "
                "VALUES (:d, 2, decode('bb', 'hex'), 'nueva.pdf', 4096, "
                " 'application/pdf', :uid, :st, false) RETURNING id"
            ),
            {"d": doc_id, "uid": owner_user_id, "st": candidate_status},
        )
    ).scalar_one()
    return doc_id, candidate_vid


async def test_begin_indexing_short_circuits_on_discarded(session):
    owner = await make_user(session)
    _, candidate_vid = await _seed_published_with_candidate(
        session, owner_user_id=owner, candidate_status="discarded"
    )

    result = await documents._begin_indexing(session, candidate_vid)

    assert result is None
    # The discarded row is not flipped back to processing.
    status = (
        await session.execute(
            text("SELECT index_status FROM document_versions WHERE id = :id"),
            {"id": candidate_vid},
        )
    ).scalar_one()
    assert status == "discarded"


def _index_inputs(title: str = "Tesis", abstract: str = "Resumen"):
    headline = headline_chunk(title, abstract)
    body = [Chunk(body_text="cuerpo del trabajo", is_headline=False, chunk_seq=1)]
    embeds = [np.zeros(1024) for _ in [headline, *body]]
    meta = IndexableMetadata(abstract=abstract, keywords=["bd"], fecha=None)
    fp = headline_fingerprint(title, abstract)
    return dict(body=body, headline=headline, embeds=embeds, meta=meta,
               headline_fingerprint=fp)


async def test_write_indexed_candidate_aborts_when_discarded_mid_flight(session):
    # Single-session model: exercises the gate's `WHERE index_status='processing'`
    # predicate in isolation. In production the worker releases _begin_indexing's
    # lock at the claim commit, so a descartar interleaves during the extract/embed
    # IO exactly as modeled here; the guarded write then matches zero rows.
    # `test_descartar_completes_while_indexing_io_in_flight` proves the no-block
    # property across two real connections.
    owner = await make_user(session)
    doc_id, candidate_vid = await _seed_published_with_candidate(
        session, owner_user_id=owner, candidate_status="pending"
    )
    # Worker claims the row (pending → processing).
    cv = await documents._begin_indexing(session, candidate_vid)
    assert cv is not None
    # A descartar commits before the worker's write lands.
    await documents.discard_candidate(session, _ctx(owner), doc_id)

    await documents.write_indexed_candidate(session, candidate_vid, **_index_inputs())

    status = (
        await session.execute(
            text("SELECT index_status FROM document_versions WHERE id = :id"),
            {"id": candidate_vid},
        )
    ).scalar_one()
    assert status == "discarded"  # the gated write matched zero rows
    chunk_count = (
        await session.execute(
            text("SELECT count(*) FROM chunks WHERE version_id = :id"),
            {"id": candidate_vid},
        )
    ).scalar_one()
    assert chunk_count == 0  # no chunks materialize on a discarded candidate


async def test_descartar_completes_while_indexing_io_in_flight(engine, monkeypatch):
    """Real two-connection proof of the claim/finalize lifecycle (ADR-0011 §5).

    The worker claims the candidate in a short committed transaction — releasing
    _begin_indexing's row lock — then parks in extract IO. A descartar issued on
    an independent connection commits 'discarded' WITHOUT waiting for that IO
    (the prior single-session model could not show this). When the worker
    resumes, its `WHERE index_status='processing'` finalize write matches zero
    rows: the candidate stays discarded with no chunks."""
    sm = async_sessionmaker(engine, expire_on_commit=False)

    # Commit a published doc + pending candidate so both connections observe it.
    async with sm() as setup:
        owner = await make_user(setup)
        doc_id, candidate_vid = await _seed_published_with_candidate(
            setup, owner_user_id=owner, candidate_status="pending"
        )
        await setup.commit()

    in_io = asyncio.Event()
    release = asyncio.Event()

    async def _blocking_extract(sha, mime):
        in_io.set()
        await release.wait()  # hold the IO window open until descartar commits
        return ExtractedDoc(
            text="Resumen\nCuerpo del trabajo.",
            paragraph_breaks=[],
            page_breaks=[],
            raw_metadata={},
        )

    monkeypatch.setattr(jobs.extractmod, "extract", _blocking_extract)

    tei = _tei_mock()
    worker = asyncio.create_task(jobs._run_index_document(sm, tei, candidate_vid))
    try:
        # Worker has committed pending→processing and is now blocked in extract;
        # it holds no DB lock here.
        await asyncio.wait_for(in_io.wait(), timeout=5)

        # If the lock were still held through the IO, this FOR UPDATE would hang
        # past the timeout. It must complete promptly on its own connection.
        async with sm() as ds:
            await asyncio.wait_for(
                documents.discard_candidate(ds, _ctx(owner), doc_id), timeout=5
            )
            await ds.commit()
    finally:
        release.set()
        await worker
        await tei.aclose()

    async with sm() as check:
        status = (
            await check.execute(
                text("SELECT index_status FROM document_versions WHERE id = :id"),
                {"id": candidate_vid},
            )
        ).scalar_one()
        chunk_count = (
            await check.execute(
                text("SELECT count(*) FROM chunks WHERE version_id = :id"),
                {"id": candidate_vid},
            )
        ).scalar_one()
        # Tidy the committed rows in FK order (no ON DELETE CASCADE here).
        for table in ("chunks", "document_authors", "document_versions"):
            await check.execute(
                text(f"DELETE FROM {table} WHERE doc_id = :id"), {"id": doc_id}
            )
        await check.execute(
            text("DELETE FROM documents WHERE id = :id"), {"id": doc_id}
        )
        await check.execute(text("DELETE FROM users WHERE id = :id"), {"id": owner})
        await check.commit()

    assert status == "discarded"
    assert chunk_count == 0


async def test_mark_failed_does_not_resurrect_discarded_candidate(session):
    # A transient-failure terminal handler runs in a fresh session after the row
    # was descartado: it must not flip 'discarded' back to 'failed' nor notify.
    owner = await make_user(session)
    doc_id, candidate_vid = await _seed_published_with_candidate(
        session, owner_user_id=owner, candidate_status="processing"
    )
    await documents.discard_candidate(session, _ctx(owner), doc_id)

    await documents.mark_failed(session, candidate_vid, error="exhausted retries: X")

    status = (
        await session.execute(
            text("SELECT index_status FROM document_versions WHERE id = :id"),
            {"id": candidate_vid},
        )
    ).scalar_one()
    assert status == "discarded"
    notif_count = (
        await session.execute(
            text("SELECT count(*) FROM notifications WHERE event_key = :ek"),
            {"ek": f"processing_failed:{candidate_vid}"},
        )
    ).scalar_one()
    assert notif_count == 0


async def test_write_headline_no_ops_on_discarded_candidate(session):
    owner = await make_user(session)
    doc_id, candidate_vid = await _seed_published_with_candidate(
        session, owner_user_id=owner, candidate_status="indexed"
    )
    inputs = _index_inputs()
    # Match the fingerprint so the only thing that can stop the write is the
    # discarded-gate, not write_headline's title/abstract-drift short-circuit.
    await session.execute(
        text(
            "UPDATE document_versions SET staged_abstract = 'Resumen', "
            "  headline_fingerprint = :fp WHERE id = :id"
        ),
        {"fp": inputs["headline_fingerprint"], "id": candidate_vid},
    )
    await documents.discard_candidate(session, _ctx(owner), doc_id)

    await documents.write_headline(
        session,
        candidate_vid,
        inputs["headline"],
        np.zeros(1024),
        inputs["headline_fingerprint"],
    )

    chunk_count = (
        await session.execute(
            text("SELECT count(*) FROM chunks WHERE version_id = :id"),
            {"id": candidate_vid},
        )
    ).scalar_one()
    assert chunk_count == 0
