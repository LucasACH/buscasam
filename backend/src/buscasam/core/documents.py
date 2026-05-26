"""Domain chokepoint for all document mutations and queries (ADR-0010 §6, module map §core/documents)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.core.document_access import manageable_where

if TYPE_CHECKING:
    from buscasam.core.auth import UserCtx


@dataclass(frozen=True)
class OwnDocSummary:
    id: int
    title: str
    publication_status: str
    visibility: str


async def list_own_documents(
    session: AsyncSession, user_ctx: UserCtx
) -> list[OwnDocSummary]:
    where, params = manageable_where("d", user_ctx)
    rows = (
        await session.execute(
            text(
                f"SELECT d.id, d.titulo, d.publication_status, d.visibility "
                f"FROM documents d WHERE {where} ORDER BY d.id"
            ),
            params,
        )
    ).mappings().all()
    return [
        OwnDocSummary(
            id=r["id"],
            title=r["titulo"],
            publication_status=r["publication_status"],
            visibility=r["visibility"],
        )
        for r in rows
    ]
