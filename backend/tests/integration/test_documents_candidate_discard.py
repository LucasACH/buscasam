"""Integration tests for core/documents.discard_candidate (module map
§core/documents, issue #59). Exercises the explicit descartar chokepoint."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from buscasam.core import documents
from buscasam.core.auth import UserCtx
from tests.factories import make_document, make_document_author, make_user


def _ctx(user_id: int) -> UserCtx:
    return UserCtx(user_id=user_id, is_unsam=True, role="estudiante")


async def _seed_published_with_candidate(
    session,
    *,
    owner_user_id: int,
    candidate_status: str = "processing",
) -> tuple[int, int, int]:
    """A published doc with a current indexed version + one non-current
    candidate in `candidate_status`. Returns (doc_id, current_vid, candidate_vid)."""
    doc_id = await make_document(session, publication_status="published")
    await make_document_author(session, doc_id, user_id=owner_user_id, status="owner")
    current_vid = (
        await session.execute(
            text(
                "INSERT INTO document_versions "
                "(doc_id, version_no, sha256, original_filename, bytes, mime, "
                " uploaded_by, index_status, is_current, first_published_at) "
                "VALUES (:d, 1, decode('aa', 'hex'), 'original.pdf', 2048, "
                " 'application/pdf', :uid, 'indexed', true, now()) RETURNING id"
            ),
            {"d": doc_id, "uid": owner_user_id},
        )
    ).scalar_one()
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
    return doc_id, current_vid, candidate_vid


async def test_discard_transitions_processing_candidate_to_discarded(session):
    owner = await make_user(session)
    doc_id, current_vid, candidate_vid = await _seed_published_with_candidate(
        session, owner_user_id=owner, candidate_status="processing"
    )

    await documents.discard_candidate(session, _ctx(owner), doc_id)

    statuses = dict(
        (
            await session.execute(
                text(
                    "SELECT id, index_status FROM document_versions WHERE doc_id = :d"
                ),
                {"d": doc_id},
            )
        ).all()
    )
    assert statuses[candidate_vid] == "discarded"
    # The published current version is untouched.
    assert statuses[current_vid] == "indexed"


_ZERO_EMBED = "[" + ",".join(["0"] * 1024) + "]"


async def _seed_chunk(session, *, doc_id: int, version_id: int) -> None:
    await session.execute(
        text(
            "INSERT INTO chunks (doc_id, chunk_seq, is_headline, body_text, "
            "  embedding, embedding_model_version, version_id, is_current) "
            "VALUES (:d, 0, true, 'cuerpo', cast(:emb as halfvec(1024)), "
            "        'multilingual-e5-large@v1', :vid, false)"
        ),
        {"d": doc_id, "emb": _ZERO_EMBED, "vid": version_id},
    )


@pytest.mark.parametrize("candidate_status", ["pending", "processing", "indexed", "failed"])
async def test_discard_transitions_any_non_current_candidate(session, candidate_status):
    owner = await make_user(session)
    doc_id, _, candidate_vid = await _seed_published_with_candidate(
        session, owner_user_id=owner, candidate_status=candidate_status
    )

    await documents.discard_candidate(session, _ctx(owner), doc_id)

    status = (
        await session.execute(
            text("SELECT index_status FROM document_versions WHERE id = :id"),
            {"id": candidate_vid},
        )
    ).scalar_one()
    assert status == "discarded"


async def test_discard_deletes_candidate_chunks_only(session):
    owner = await make_user(session)
    doc_id, current_vid, candidate_vid = await _seed_published_with_candidate(
        session, owner_user_id=owner, candidate_status="indexed"
    )
    await _seed_chunk(session, doc_id=doc_id, version_id=current_vid)
    await _seed_chunk(session, doc_id=doc_id, version_id=candidate_vid)

    await documents.discard_candidate(session, _ctx(owner), doc_id)

    remaining = (
        await session.execute(
            text("SELECT version_id FROM chunks WHERE doc_id = :d"),
            {"d": doc_id},
        )
    ).scalars().all()
    # Only the candidate's chunks are deleted; the current version's stay.
    assert remaining == [current_vid]


async def test_discard_cross_user_raises_not_found(session):
    owner = await make_user(session)
    intruder = await make_user(session)
    doc_id, _, _ = await _seed_published_with_candidate(
        session, owner_user_id=owner
    )

    with pytest.raises(documents.DocumentNotFound):
        await documents.discard_candidate(session, _ctx(intruder), doc_id)


async def test_discard_without_candidate_raises(session):
    owner = await make_user(session)
    # Published doc with only the current version — no in-flight candidate.
    doc_id = await make_document(session, publication_status="published")
    await make_document_author(session, doc_id, user_id=owner, status="owner")
    await session.execute(
        text(
            "INSERT INTO document_versions "
            "(doc_id, version_no, sha256, original_filename, bytes, mime, "
            " uploaded_by, index_status, is_current, first_published_at) "
            "VALUES (:d, 1, decode('aa', 'hex'), 'original.pdf', 2048, "
            " 'application/pdf', :uid, 'indexed', true, now())"
        ),
        {"d": doc_id, "uid": owner},
    )

    with pytest.raises(documents.NoCandidateToDiscard):
        await documents.discard_candidate(session, _ctx(owner), doc_id)


async def test_discard_ignores_already_discarded_candidate(session):
    owner = await make_user(session)
    doc_id, _, candidate_vid = await _seed_published_with_candidate(
        session, owner_user_id=owner, candidate_status="processing"
    )
    await documents.discard_candidate(session, _ctx(owner), doc_id)

    # A second descartar finds no live candidate.
    with pytest.raises(documents.NoCandidateToDiscard):
        await documents.discard_candidate(session, _ctx(owner), doc_id)
