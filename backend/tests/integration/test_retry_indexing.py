"""Integration tests for core/documents.retry_indexing: author-initiated
re-enqueue after a system-side indexing failure, plus the failure-kind /
retry_available_at projection the editar UI consumes."""

from __future__ import annotations

import secrets
from datetime import timedelta

import pytest
from sqlalchemy import text

from buscasam.core import documents
from buscasam.core.auth import UserCtx
from buscasam.core.documents import (
    MAX_INDEX_RETRIES,
    RETRY_COOLDOWN,
    NoRetriableFailure,
    RetryCooldownActive,
    RetryLimitReached,
)
from tests.factories import make_document, make_document_author, make_user


def _ctx(user_id: int) -> UserCtx:
    return UserCtx(user_id=user_id, is_unsam=True, role="estudiante")


async def _seed_failed_draft(
    session,
    *,
    owner_user_id: int,
    kind: str = "system",
    failed_ago: timedelta = RETRY_COOLDOWN + timedelta(minutes=1),
    retry_count: int = 0,
) -> tuple[int, int]:
    """A never-published draft whose only version terminally failed indexing
    `failed_ago` ago. Returns (doc_id, version_id)."""
    doc_id = await make_document(session, publication_status="draft")
    await make_document_author(session, doc_id, user_id=owner_user_id, status="owner")
    version_id = (
        await session.execute(
            text(
                "INSERT INTO document_versions "
                "(doc_id, version_no, sha256, original_filename, bytes, mime, "
                " uploaded_by, index_status, index_error, index_error_kind, "
                " index_failed_at, index_retry_count) "
                "VALUES (:d, 1, :sha, 'f.pdf', 1024, 'application/pdf', :uid, "
                " 'failed', 'exhausted retries: ConnectError', :kind, "
                " now() - :ago, :rc) RETURNING id"
            ),
            {
                "d": doc_id,
                "sha": secrets.token_bytes(32),
                "uid": owner_user_id,
                "kind": kind,
                "ago": failed_ago,
                "rc": retry_count,
            },
        )
    ).scalar_one()
    return doc_id, version_id


async def test_retry_resets_to_pending_and_enqueues_index_document(session):
    owner = await make_user(session)
    doc_id, version_id = await _seed_failed_draft(session, owner_user_id=owner)

    await documents.retry_indexing(session, _ctx(owner), doc_id)

    row = (
        (
            await session.execute(
                text(
                    "SELECT index_status, index_stage, index_error, "
                    "  index_error_kind, index_failed_at, index_retry_count "
                    "FROM document_versions WHERE id = :id"
                ),
                {"id": version_id},
            )
        )
        .mappings()
        .one()
    )
    assert row["index_status"] == "pending"
    assert row["index_stage"] is None
    assert row["index_error"] is None
    assert row["index_error_kind"] is None
    assert row["index_failed_at"] is None
    assert row["index_retry_count"] == 1

    # ADR-0008 §1: the job row is visible from the same transaction.
    task_name = (
        await session.execute(
            text(
                "SELECT task_name FROM procrastinate_jobs "
                "WHERE args->>'version_id' = :vid"
            ),
            {"vid": str(version_id)},
        )
    ).scalar_one()
    assert task_name.endswith("index_document")


async def test_retry_inside_cooldown_raises(session):
    owner = await make_user(session)
    doc_id, _ = await _seed_failed_draft(
        session, owner_user_id=owner, failed_ago=timedelta(minutes=1)
    )

    with pytest.raises(RetryCooldownActive):
        await documents.retry_indexing(session, _ctx(owner), doc_id)


async def test_retry_past_limit_raises(session):
    owner = await make_user(session)
    doc_id, _ = await _seed_failed_draft(
        session, owner_user_id=owner, retry_count=MAX_INDEX_RETRIES
    )

    with pytest.raises(RetryLimitReached):
        await documents.retry_indexing(session, _ctx(owner), doc_id)


async def test_retry_on_file_failure_raises(session):
    owner = await make_user(session)
    doc_id, _ = await _seed_failed_draft(session, owner_user_id=owner, kind="file")

    with pytest.raises(NoRetriableFailure):
        await documents.retry_indexing(session, _ctx(owner), doc_id)


async def test_retry_without_failed_version_raises(session):
    owner = await make_user(session)
    doc_id = await make_document(session, publication_status="draft")
    await make_document_author(session, doc_id, user_id=owner, status="owner")

    with pytest.raises(NoRetriableFailure):
        await documents.retry_indexing(session, _ctx(owner), doc_id)


async def test_retry_cross_user_raises_not_found(session):
    owner = await make_user(session)
    stranger = await make_user(session)
    doc_id, _ = await _seed_failed_draft(session, owner_user_id=owner)

    with pytest.raises(documents.DocumentNotFound):
        await documents.retry_indexing(session, _ctx(stranger), doc_id)


async def test_draft_state_surfaces_failure_kind_and_retry_available_at(session):
    owner = await make_user(session)
    doc_id, version_id = await _seed_failed_draft(session, owner_user_id=owner)

    state = await documents.get_draft_state(session, _ctx(owner), doc_id)

    failed_at = (
        await session.execute(
            text("SELECT index_failed_at FROM document_versions WHERE id = :id"),
            {"id": version_id},
        )
    ).scalar_one()
    assert state.index_status == "failed"
    assert state.index_failure_kind == "system"
    assert state.retry_available_at == failed_at + RETRY_COOLDOWN
    assert state.publish_gate_reason == "processing_failed"
    assert state.retry_remaining == MAX_INDEX_RETRIES


async def test_draft_state_retry_remaining_counts_down(session):
    owner = await make_user(session)
    doc_id, _ = await _seed_failed_draft(
        session, owner_user_id=owner, retry_count=MAX_INDEX_RETRIES - 1
    )

    state = await documents.get_draft_state(session, _ctx(owner), doc_id)

    assert state.retry_remaining == 1
