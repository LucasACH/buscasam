"""The worker discarded-gate (issue #59, module map §core/jobs + §core/documents,
ADR-0011 §5). A descartar committed against a candidate is terminal: the worker
write functions match zero rows and never resurrect the row or materialize chunks.
Driven directly against the session fixture — no worker, no real lock contention;
the race is modeled linearly (begin → discard → worker write)."""
from __future__ import annotations

import numpy as np
from sqlalchemy import text

from buscasam.core import documents
from buscasam.core.auth import UserCtx
from buscasam.core.chunk import Chunk, headline_chunk, headline_fingerprint
from buscasam.core.extract import IndexableMetadata
from tests.factories import make_document, make_document_author, make_user


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
