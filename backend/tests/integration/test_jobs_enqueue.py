"""Tests for the typed enqueue helpers (issue #28).

ADR-0008 §1: deferring through the active SQLAlchemy transaction's psycopg
connection means the domain row and the job INSERT commit/roll back together.
ADR-0008 §7: queueing_lock=`index:v{id}` so a duplicate enqueue is a no-op.
"""
from __future__ import annotations

import secrets

from sqlalchemy import text

from buscasam.core import documents, jobs
from buscasam.core.blob_store import BlobPutResult
from buscasam.core.auth import UserCtx
from tests.factories import make_document, make_user


async def _seed_doc_with_owner(session) -> tuple[int, int]:
    uid = await make_user(session)
    doc_id = await make_document(session, publication_status="draft")
    await session.execute(
        text(
            "INSERT INTO document_authors (doc_id, user_id, display_name, status) "
            "VALUES (:doc_id, :uid, 'Owner', 'owner')"
        ),
        {"doc_id": doc_id, "uid": uid},
    )
    return uid, doc_id


async def test_attach_main_version_enqueues_index_document_in_same_txn(session):
    uid, doc_id = await _seed_doc_with_owner(session)
    user_ctx = UserCtx(user_id=uid, is_unsam=True, role="estudiante")

    sha256_hex = secrets.token_bytes(32).hex()
    blob = BlobPutResult(sha256=sha256_hex, bytes=1234, sniffed_mime="application/pdf")

    version_id = await documents.attach_main_version(
        session, user_ctx, doc_id, blob, original_filename="thesis.pdf"
    )

    # ADR-0008 §1: the procrastinate_jobs row visible from the same transaction.
    row = (
        await session.execute(
            text(
                "SELECT task_name, args FROM procrastinate_jobs "
                "WHERE args->>'version_id' = :vid"
            ),
            {"vid": str(version_id)},
        )
    ).mappings().one_or_none()
    assert row is not None
    assert row["task_name"].endswith("index_document")


async def test_enqueue_index_document_twice_is_no_op(session):
    uid, doc_id = await _seed_doc_with_owner(session)
    user_ctx = UserCtx(user_id=uid, is_unsam=True, role="estudiante")

    sha256_hex = secrets.token_bytes(32).hex()
    blob = BlobPutResult(sha256=sha256_hex, bytes=1234, sniffed_mime="application/pdf")

    version_id = await documents.attach_main_version(
        session, user_ctx, doc_id, blob, original_filename="thesis.pdf"
    )
    # second call should be a no-op (AlreadyEnqueued swallowed)
    await jobs.enqueue_index_document(session, version_id)

    count = (
        await session.execute(
            text(
                "SELECT COUNT(*) FROM procrastinate_jobs "
                "WHERE args->>'version_id' = :vid AND status = 'todo'"
            ),
            {"vid": str(version_id)},
        )
    ).scalar_one()
    assert count == 1
