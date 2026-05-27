"""Regression guards for `core/documents` being authoritative on authorization.

Every author-facing function in `core/documents` must apply `manageable_where`
before mutating, so callers cannot accidentally skip the check by forgetting the
ordering rule (module map §core/documents Invariants, ADR-0010 §7).
"""
from __future__ import annotations

import secrets

import pytest
from sqlalchemy import text

from buscasam.core import documents
from buscasam.core.auth import UserCtx
from buscasam.core.blob_store import BlobPutResult
from buscasam.core.documents import DocumentNotFound
from tests.factories import make_document, make_user


async def test_attach_main_version_rejects_non_manageable_user(session):
    owner_uid = await make_user(session)
    other_uid = await make_user(session)
    doc_id = await make_document(session, publication_status="draft")
    await session.execute(
        text(
            "INSERT INTO document_authors (doc_id, user_id, display_name, status) "
            "VALUES (:doc_id, :uid, 'Owner', 'owner')"
        ),
        {"doc_id": doc_id, "uid": owner_uid},
    )

    other_ctx = UserCtx(user_id=other_uid, is_unsam=True, role="estudiante")
    blob = BlobPutResult(
        sha256=secrets.token_bytes(32).hex(),
        bytes=1234,
        sniffed_mime="application/pdf",
    )

    with pytest.raises(DocumentNotFound):
        await documents.attach_main_version(
            session, other_ctx, doc_id, blob, original_filename="thesis.pdf"
        )

    count = (
        await session.execute(
            text("SELECT COUNT(*) FROM document_versions WHERE doc_id = :d"),
            {"d": doc_id},
        )
    ).scalar_one()
    assert count == 0
