"""The report→queue→act→resolve→notify lifecycle and owner of the two
moderation tables (module map §core/moderation, ADR-0010 §9)."""
from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.core.document_access import readable_where

if TYPE_CHECKING:
    from buscasam.core.auth import UserCtx

Reason = Literal["spam", "contenido_inadecuado", "plagio", "error"]


class DocumentNotReadable(Exception):
    """The reporter cannot read the target document — the router maps this to a
    uniform 404 so hidden/private/deleted existence never leaks."""


async def file_report(
    session: AsyncSession, user_ctx: UserCtx, doc_id: int, reason: Reason
) -> None:
    """Insert an `open` report, gated by `readable_where` (ADR-0010 §7).

    A second open report by the same reporter on the same doc is a harmless
    no-op (`ON CONFLICT` on the unique partial index
    `(doc_id, reporter_user_id) WHERE status='open'`). A non-readable doc raises
    `DocumentNotReadable` — `require_authenticated` is the caller's job."""
    where, params = readable_where("d", user_ctx)
    readable = (
        await session.execute(
            text(f"SELECT 1 FROM documents d WHERE d.id = :doc_id AND ({where})"),
            {"doc_id": doc_id, **params},
        )
    ).scalar_one_or_none()
    if readable is None:
        raise DocumentNotReadable

    await session.execute(
        text(
            "INSERT INTO document_reports (doc_id, reporter_user_id, reason) "
            "VALUES (:doc_id, :reporter_user_id, :reason) "
            "ON CONFLICT (doc_id, reporter_user_id) WHERE status = 'open' "
            "DO NOTHING"
        ),
        {"doc_id": doc_id, "reporter_user_id": user_ctx.user_id, "reason": reason},
    )
