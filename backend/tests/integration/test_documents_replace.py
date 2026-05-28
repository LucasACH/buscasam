"""Integration tests for core/documents.replace_main_version (module map
§core/documents, issue #58). Exercises the candidate-replacement chokepoint."""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import text

from buscasam.core import documents
from buscasam.core.auth import UserCtx
from buscasam.core.blob_store import BlobPutResult
from buscasam.core.chunk import headline_fingerprint
from tests.factories import make_document, make_document_author, make_user


def _ctx(user_id: int) -> UserCtx:
    return UserCtx(user_id=user_id, is_unsam=True, role="estudiante")


async def _enqueued_task_names(session, version_id: int) -> list[str]:
    rows = (
        await session.execute(
            text(
                "SELECT task_name FROM procrastinate_jobs "
                "WHERE args->>'version_id' = :vid"
            ),
            {"vid": str(version_id)},
        )
    ).scalars().all()
    return list(rows)


async def _seed_published_doc(
    session,
    *,
    owner_user_id: int,
    title: str = "Trabajo publicado",
    abstract: str = "Resumen publicado",
    keywords: list[str] | None = None,
    fecha: date = date(2024, 3, 1),
) -> tuple[int, int]:
    """A published document with one indexed, current version. Returns
    (doc_id, current_version_id)."""
    keywords = keywords if keywords is not None else ["bd", "sql"]
    doc_id = await make_document(
        session, publication_status="published", titulo=title, abstract=abstract,
        fecha=fecha,
    )
    await session.execute(
        text("UPDATE documents SET keywords = :kw WHERE id = :d"),
        {"kw": keywords, "d": doc_id},
    )
    await make_document_author(session, doc_id, user_id=owner_user_id, status="owner")
    version_id = (
        await session.execute(
            text(
                "INSERT INTO document_versions "
                "(doc_id, version_no, sha256, original_filename, bytes, mime, "
                " uploaded_by, index_status, is_current, first_published_at, "
                " headline_fingerprint, indexed_at) "
                "VALUES (:d, 1, decode('aa', 'hex'), 'original.pdf', 2048, "
                " 'application/pdf', :uid, 'indexed', true, now(), :fp, now()) "
                "RETURNING id"
            ),
            {"d": doc_id, "uid": owner_user_id, "fp": headline_fingerprint(title, abstract)},
        )
    ).scalar_one()
    return doc_id, version_id


def _blob(sha: str = "cc" * 32, *, bytes_: int = 4096, mime: str = "application/pdf") -> BlobPutResult:
    return BlobPutResult(sha256=sha, bytes=bytes_, sniffed_mime=mime)


async def test_replace_inserts_candidate_and_leaves_published_untouched(session):
    owner = await make_user(session)
    doc_id, published_vid = await _seed_published_doc(
        session, owner_user_id=owner, abstract="Resumen publicado",
        keywords=["bd", "sql"], fecha=date(2024, 3, 1),
    )

    new_vid = await documents.replace_main_version(
        session, _ctx(owner), doc_id, _blob(), original_filename="nueva.pdf"
    )

    candidate = (
        await session.execute(
            text(
                "SELECT version_no, is_current, index_status, first_published_at, "
                "       staged_abstract, staged_keywords, staged_fecha, "
                "       original_filename "
                "FROM document_versions WHERE id = :id"
            ),
            {"id": new_vid},
        )
    ).mappings().one()
    assert candidate["version_no"] == 2
    assert candidate["is_current"] is False
    assert candidate["index_status"] == "pending"
    assert candidate["first_published_at"] is None
    assert candidate["original_filename"] == "nueva.pdf"
    # staged_* pre-filled from documents.* so polling clients see sensible values.
    assert candidate["staged_abstract"] == "Resumen publicado"
    assert candidate["staged_keywords"] == ["bd", "sql"]
    assert candidate["staged_fecha"] == date(2024, 3, 1)

    # index_document enqueued in the same transaction.
    assert any(n.endswith("index_document") for n in await _enqueued_task_names(session, new_vid))

    # Published current version untouched.
    published = (
        await session.execute(
            text(
                "SELECT is_current, first_published_at FROM document_versions "
                "WHERE id = :id"
            ),
            {"id": published_vid},
        )
    ).mappings().one()
    assert published["is_current"] is True
    assert published["first_published_at"] is not None

    # documents row untouched.
    doc = (
        await session.execute(
            text(
                "SELECT publication_status, abstract, keywords, fecha "
                "FROM documents WHERE id = :id"
            ),
            {"id": doc_id},
        )
    ).mappings().one()
    assert doc["publication_status"] == "published"
    assert doc["abstract"] == "Resumen publicado"
    assert doc["keywords"] == ["bd", "sql"]
    assert doc["fecha"] == date(2024, 3, 1)


async def test_replace_without_published_current_version_raises(session):
    owner = await make_user(session)
    # A draft document with a single non-current candidate — never published.
    doc_id = await make_document(session, publication_status="draft")
    await make_document_author(session, doc_id, user_id=owner, status="owner")
    await session.execute(
        text(
            "INSERT INTO document_versions "
            "(doc_id, version_no, sha256, original_filename, bytes, mime, "
            " uploaded_by, index_status, is_current) "
            "VALUES (:d, 1, decode('aa', 'hex'), 'd.pdf', 1, 'application/pdf', "
            " :uid, 'indexed', false)"
        ),
        {"d": doc_id, "uid": owner},
    )

    with pytest.raises(documents.NoPublishedVersion):
        await documents.replace_main_version(
            session, _ctx(owner), doc_id, _blob(), original_filename="x.pdf"
        )


async def test_replace_cross_user_raises_not_found(session):
    owner = await make_user(session)
    intruder = await make_user(session)
    doc_id, _ = await _seed_published_doc(session, owner_user_id=owner)

    with pytest.raises(documents.DocumentNotFound):
        await documents.replace_main_version(
            session, _ctx(intruder), doc_id, _blob(), original_filename="x.pdf"
        )


async def test_second_replace_discards_first_candidate(session):
    owner = await make_user(session)
    doc_id, _ = await _seed_published_doc(session, owner_user_id=owner)

    first = await documents.replace_main_version(
        session, _ctx(owner), doc_id, _blob(sha="dd" * 32), original_filename="a.pdf"
    )
    second = await documents.replace_main_version(
        session, _ctx(owner), doc_id, _blob(sha="ee" * 32), original_filename="b.pdf"
    )

    statuses = dict(
        (
            await session.execute(
                text(
                    "SELECT id, index_status FROM document_versions "
                    "WHERE id = ANY(:ids)"
                ),
                {"ids": [first, second]},
            )
        ).all()
    )
    assert statuses[first] == "discarded"
    assert statuses[second] == "pending"

    # The new candidate is the only live (non-discarded, never-public) candidate.
    live = (
        await session.execute(
            text(
                "SELECT id FROM document_versions WHERE doc_id = :d "
                "AND is_current = false AND index_status <> 'discarded' "
                "AND first_published_at IS NULL"
            ),
            {"d": doc_id},
        )
    ).scalars().all()
    assert live == [second]


async def test_draft_state_candidate_null_without_in_flight_candidate(session):
    owner = await make_user(session)
    doc_id, _ = await _seed_published_doc(session, owner_user_id=owner)

    state = await documents.get_draft_state(session, _ctx(owner), doc_id)

    assert state.candidate is None


async def test_draft_state_surfaces_processing_candidate(session):
    owner = await make_user(session)
    doc_id, _ = await _seed_published_doc(
        session, owner_user_id=owner, abstract="Resumen publicado",
        keywords=["bd", "sql"], fecha=date(2024, 3, 1),
    )
    await documents.replace_main_version(
        session, _ctx(owner), doc_id, _blob(), original_filename="nueva.pdf"
    )

    state = await documents.get_draft_state(session, _ctx(owner), doc_id)

    assert state.candidate is not None
    c = state.candidate
    assert c.status == "processing"
    assert c.staged_abstract == "Resumen publicado"
    assert c.staged_keywords == ["bd", "sql"]
    assert c.staged_fecha == date(2024, 3, 1)
    assert c.can_discard is True
    assert c.can_publish is False  # still processing
    assert c.indexed_at is None
    assert c.error is None


async def test_draft_state_ready_candidate_owner_can_publish(session):
    owner = await make_user(session)
    doc_id, _ = await _seed_published_doc(
        session, owner_user_id=owner, title="Trabajo publicado",
        abstract="Resumen publicado",
    )
    new_vid = await documents.replace_main_version(
        session, _ctx(owner), doc_id, _blob(), original_filename="nueva.pdf"
    )
    # Simulate the worker finishing extraction: indexed + matching fingerprint.
    await session.execute(
        text(
            "UPDATE document_versions SET index_status = 'indexed', "
            "  indexed_at = now(), headline_fingerprint = :fp WHERE id = :id"
        ),
        {
            "fp": headline_fingerprint("Trabajo publicado", "Resumen publicado"),
            "id": new_vid,
        },
    )

    state = await documents.get_draft_state(session, _ctx(owner), doc_id)

    assert state.candidate is not None
    assert state.candidate.status == "ready"
    assert state.candidate.can_publish is True
    assert state.candidate.indexed_at is not None
