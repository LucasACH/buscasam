"""Tests for the retention purge core (`jobs._run_purge_deleted`).

Module map §core/jobs: `_run_purge_deleted` is the testable chokepoint —
`DELETE FROM documents WHERE soft_deleted_at < now() - INTERVAL '180 days'`,
cascading to versions/attachments/chunks. In-window and never-deleted documents
are untouched; the run is idempotent (ADR-0006 §12).
"""
from __future__ import annotations

from sqlalchemy import text

import secrets

from buscasam.core import jobs
from tests.factories import make_chunk, make_document, make_user


async def _set_soft_deleted_days_ago(session, doc_id: int, days: int) -> None:
    await session.execute(
        text(
            "UPDATE documents SET soft_deleted_at = now() - make_interval(days => :d) "
            "WHERE id = :id"
        ),
        {"d": days, "id": doc_id},
    )


async def test_purge_deletes_document_soft_deleted_past_retention(session):
    doc_id = await make_document(session)
    await _set_soft_deleted_days_ago(session, doc_id, 181)

    await jobs._run_purge_deleted(session)

    exists = (
        await session.execute(
            text("SELECT 1 FROM documents WHERE id = :id"), {"id": doc_id}
        )
    ).first()
    assert exists is None


async def test_purge_leaves_in_window_and_never_deleted_documents(session):
    in_window = await make_document(session)
    await _set_soft_deleted_days_ago(session, in_window, 179)
    never_deleted = await make_document(session)

    await jobs._run_purge_deleted(session)

    survivors = (
        await session.execute(
            text("SELECT id FROM documents WHERE id = ANY(:ids) ORDER BY id"),
            {"ids": [in_window, never_deleted]},
        )
    ).scalars().all()
    assert survivors == sorted([in_window, never_deleted])


async def _add_version(session, doc_id: int, uid: int) -> int:
    return (
        await session.execute(
            text(
                "INSERT INTO document_versions "
                "(doc_id, version_no, sha256, original_filename, bytes, mime, "
                " uploaded_by) "
                "VALUES (:d, 1, decode(:sha, 'hex'), 'f.pdf', 1, "
                "        'application/pdf', :u) RETURNING id"
            ),
            {"d": doc_id, "sha": secrets.token_bytes(32).hex(), "u": uid},
        )
    ).scalar_one()


async def _add_attachment(session, doc_id: int, uid: int) -> int:
    return (
        await session.execute(
            text(
                "INSERT INTO document_attachments "
                "(doc_id, sha256, original_filename, bytes, mime, uploaded_by) "
                "VALUES (:d, decode(:sha, 'hex'), 'a.csv', 1, 'text/csv', :u) "
                "RETURNING id"
            ),
            {"d": doc_id, "sha": secrets.token_bytes(32).hex(), "u": uid},
        )
    ).scalar_one()


async def test_purge_cascades_to_versions_attachments_chunks(session):
    uid = await make_user(session)
    doc_id = await make_document(session)
    version_id = await _add_version(session, doc_id, uid)
    attachment_id = await _add_attachment(session, doc_id, uid)
    await session.execute(
        text(
            "INSERT INTO chunks "
            "(doc_id, version_id, chunk_seq, is_headline, body_text, "
            " embedding_model_version, is_current) "
            "VALUES (:d, :v, 0, true, 'b', 'm', true)"
        ),
        {"d": doc_id, "v": version_id},
    )
    await _set_soft_deleted_days_ago(session, doc_id, 181)

    await jobs._run_purge_deleted(session)

    for table, col, val in [
        ("document_versions", "id", version_id),
        ("document_attachments", "id", attachment_id),
        ("chunks", "version_id", version_id),
    ]:
        remaining = (
            await session.execute(
                text(f"SELECT 1 FROM {table} WHERE {col} = :v"), {"v": val}
            )
        ).first()
        assert remaining is None, f"{table} not cascaded"


async def test_purge_is_idempotent_across_repeated_runs(session):
    doc_id = await make_document(session)
    await _set_soft_deleted_days_ago(session, doc_id, 181)

    first = await jobs._run_purge_deleted(session)
    second = await jobs._run_purge_deleted(session)

    assert first == 1
    assert second == 0
