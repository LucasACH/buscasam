"""Integration tests for core/documents attachment management (issue #31,
module map §core/documents). Document-scoped add/remove with the 5-cap."""
from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.core import documents
from buscasam.core.auth import UserCtx
from buscasam.core.blob_store import BlobPutResult
from tests.factories import make_document, make_document_author, make_user


def _ctx(user_id: int) -> UserCtx:
    return UserCtx(user_id=user_id, is_unsam=True, role="estudiante")


def _blob(sha: str = "aa" * 32, size: int = 1234, mime: str = "text/csv") -> BlobPutResult:
    return BlobPutResult(sha256=sha, bytes=size, sniffed_mime=mime)


async def _seed_doc(session, owner_id: int, *, publication_status: str = "draft") -> int:
    doc_id = await make_document(session, publication_status=publication_status)
    await make_document_author(session, doc_id, user_id=owner_id, status="owner")
    return doc_id


async def _seed_version(session, doc_id: int, owner_id: int) -> int:
    """A minimal indexed candidate so get_draft_state has a version row."""
    return (
        await session.execute(
            text(
                "INSERT INTO document_versions "
                "(doc_id, version_no, sha256, original_filename, bytes, mime, "
                " uploaded_by, index_status) "
                "VALUES (:d, 1, decode('00', 'hex'), 'f.pdf', 1, "
                " 'application/pdf', :u, 'indexed') RETURNING id"
            ),
            {"d": doc_id, "u": owner_id},
        )
    ).scalar_one()


async def test_add_attachment_inserts_row(session):
    owner = await make_user(session)
    doc_id = await _seed_doc(session, owner)

    att_id = await documents.add_attachment(
        session, _ctx(owner), doc_id, _blob(), original_filename="data.csv"
    )

    row = (
        await session.execute(
            text(
                "SELECT doc_id, original_filename, bytes, mime, "
                "       encode(sha256, 'hex') AS sha "
                "FROM document_attachments WHERE id = :id"
            ),
            {"id": att_id},
        )
    ).mappings().one()
    assert row["doc_id"] == doc_id
    assert row["original_filename"] == "data.csv"
    assert row["bytes"] == 1234
    assert row["mime"] == "text/csv"
    assert row["sha"] == "aa" * 32


async def _count(session, doc_id: int) -> int:
    return (
        await session.execute(
            text("SELECT count(*) FROM document_attachments WHERE doc_id = :d"),
            {"d": doc_id},
        )
    ).scalar_one()


async def test_add_sixth_attachment_exceeds_cap(session):
    owner = await make_user(session)
    doc_id = await _seed_doc(session, owner)
    for i in range(5):
        await documents.add_attachment(
            session, _ctx(owner), doc_id, _blob(sha=f"{i:02d}" * 32), original_filename=f"f{i}.csv"
        )

    with pytest.raises(documents.AttachmentCapExceeded):
        await documents.add_attachment(
            session, _ctx(owner), doc_id, _blob(sha="ff" * 32), original_filename="sixth.csv"
        )

    assert await _count(session, doc_id) == 5


async def test_add_attachment_cross_user_not_found(session):
    owner = await make_user(session)
    other = await make_user(session)
    doc_id = await _seed_doc(session, owner)

    with pytest.raises(documents.DocumentNotFound):
        await documents.add_attachment(
            session, _ctx(other), doc_id, _blob(), original_filename="x.csv"
        )

    assert await _count(session, doc_id) == 0


async def test_remove_attachment_deletes_row(session):
    owner = await make_user(session)
    doc_id = await _seed_doc(session, owner)
    att_id = await documents.add_attachment(
        session, _ctx(owner), doc_id, _blob(), original_filename="x.csv"
    )

    await documents.remove_attachment(session, _ctx(owner), doc_id, att_id)

    assert await _count(session, doc_id) == 0


async def test_remove_attachment_cross_user_not_found(session):
    owner = await make_user(session)
    other = await make_user(session)
    doc_id = await _seed_doc(session, owner)
    att_id = await documents.add_attachment(
        session, _ctx(owner), doc_id, _blob(), original_filename="x.csv"
    )

    with pytest.raises(documents.DocumentNotFound):
        await documents.remove_attachment(session, _ctx(other), doc_id, att_id)

    assert await _count(session, doc_id) == 1


async def test_remove_missing_attachment_not_found(session):
    owner = await make_user(session)
    doc_id = await _seed_doc(session, owner)

    with pytest.raises(documents.DocumentNotFound):
        await documents.remove_attachment(session, _ctx(owner), doc_id, 999999)


async def test_parallel_adds_at_cap_minus_one_do_not_both_succeed(engine):
    """Two parallel adds at count=4 must not both land (transactional cap,
    ADR-0006 §7). Uses two committed connections so the FOR UPDATE lock on the
    documents row actually serializes them — the conftest `session` fixture is a
    single rolled-back transaction and cannot exercise real concurrency."""
    async with AsyncSession(engine) as s:
        owner = await make_user(s)
        doc_id = await _seed_doc(s, owner)
        for i in range(4):
            await documents.add_attachment(
                s, _ctx(owner), doc_id, _blob(sha=f"{i:02d}" * 32),
                original_filename=f"f{i}.csv",
            )
        await s.commit()

    async def _add(sha: str) -> None:
        async with AsyncSession(engine) as s:
            await documents.add_attachment(
                s, _ctx(owner), doc_id, _blob(sha=sha), original_filename="p.csv"
            )
            await s.commit()

    try:
        results = await asyncio.gather(
            _add("aa" * 32), _add("bb" * 32), return_exceptions=True
        )
        succeeded = [r for r in results if r is None]
        capped = [r for r in results if isinstance(r, documents.AttachmentCapExceeded)]
        assert len(succeeded) == 1
        assert len(capped) == 1

        async with AsyncSession(engine) as s:
            assert await _count(s, doc_id) == 5
    finally:
        async with AsyncSession(engine) as s:
            await s.execute(
                text("DELETE FROM document_attachments WHERE doc_id = :d"), {"d": doc_id}
            )
            await s.execute(
                text("DELETE FROM document_authors WHERE doc_id = :d"), {"d": doc_id}
            )
            await s.execute(text("DELETE FROM documents WHERE id = :d"), {"d": doc_id})
            await s.execute(text("DELETE FROM users WHERE id = :u"), {"u": owner})
            await s.commit()


async def test_get_draft_state_includes_attachments(session):
    owner = await make_user(session)
    doc_id = await _seed_doc(session, owner)
    await _seed_version(session, doc_id, owner)
    att_id = await documents.add_attachment(
        session, _ctx(owner), doc_id, _blob(size=4096, mime="text/csv"),
        original_filename="data.csv",
    )

    state = await documents.get_draft_state(session, _ctx(owner), doc_id)

    assert len(state.attachments) == 1
    att = state.attachments[0]
    assert att.id == att_id
    assert att.original_filename == "data.csv"
    assert att.size_bytes == 4096
    assert att.mime == "text/csv"


async def test_add_and_remove_after_publish_stays_published(session):
    owner = await make_user(session)
    doc_id = await _seed_doc(session, owner, publication_status="published")

    async def _status() -> str:
        return (
            await session.execute(
                text("SELECT publication_status FROM documents WHERE id = :d"),
                {"d": doc_id},
            )
        ).scalar_one()

    att_id = await documents.add_attachment(
        session, _ctx(owner), doc_id, _blob(), original_filename="post.csv"
    )
    assert await _status() == "published"

    await documents.remove_attachment(session, _ctx(owner), doc_id, att_id)
    assert await _status() == "published"
