"""Attachment add/remove with the 5-file cap (ADR-0006 §7,
module map §core/documents)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.core.document_access import manageable_where

from buscasam.core.documents._shared import assert_manageable
from buscasam.core.documents.exceptions import (
    AttachmentCapExceeded,
    DocumentNotFound,
)

if TYPE_CHECKING:
    from buscasam.core.auth import UserCtx
    from buscasam.core.blob_store import BlobPutResult


async def add_attachment(
    session: AsyncSession,
    user_ctx: UserCtx,
    doc_id: int,
    blob: BlobPutResult,
    *,
    original_filename: str,
) -> int:
    where, params = manageable_where("d", user_ctx)
    # FOR UPDATE OF d serializes concurrent attachment inserts for this document
    # so the 5-cap below cannot be raced (ADR-0006 §7): a second uploader blocks
    # here until the first commits, then re-counts against the committed rows.
    locked = (
        await session.execute(
            text(
                f"SELECT 1 FROM documents d WHERE d.id = :doc_id AND ({where}) "
                "FOR UPDATE OF d"
            ),
            {"doc_id": doc_id, **params},
        )
    ).scalar_one_or_none()
    if locked is None:
        raise DocumentNotFound

    count = (
        await session.execute(
            text("SELECT count(*) FROM document_attachments WHERE doc_id = :doc_id"),
            {"doc_id": doc_id},
        )
    ).scalar_one()
    if count >= 5:
        raise AttachmentCapExceeded

    return (
        await session.execute(
            text(
                "INSERT INTO document_attachments "
                "(doc_id, sha256, original_filename, bytes, mime, uploaded_by) "
                "VALUES (:doc_id, decode(:sha, 'hex'), :fn, :bytes, :mime, :uid) "
                "RETURNING id"
            ),
            {
                "doc_id": doc_id,
                "sha": blob.sha256,
                "fn": original_filename,
                "bytes": blob.bytes,
                "mime": blob.sniffed_mime,
                "uid": user_ctx.user_id,
            },
        )
    ).scalar_one()


async def remove_attachment(
    session: AsyncSession, user_ctx: UserCtx, doc_id: int, att_id: int
) -> None:
    """Manageable-scoped delete of one attachment row. The underlying blob is
    left for the orphan sweep (dedup-safe). Cross-user docs and missing rows
    both raise DocumentNotFound (→ 404)."""
    await assert_manageable(session, user_ctx, doc_id)
    result = await session.execute(
        text(
            "DELETE FROM document_attachments "
            "WHERE id = :att_id AND doc_id = :doc_id"
        ),
        {"att_id": att_id, "doc_id": doc_id},
    )
    if result.rowcount == 0:
        raise DocumentNotFound
