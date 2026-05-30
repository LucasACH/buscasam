"""GET /api/sitemap — public-only document list for the Next sitemap (ADR-0004 §4).

Returns ids of `publico`, published, non-deleted, non-hidden documents through the
`invitado_where` access predicate so the crawler surface never leaks unauthorized
documents (SPEC §Criterios de Aceptación). The frontend renders absolute URLs.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.api.deps import get_session
from buscasam.core.document_access import invitado_where

router = APIRouter(prefix="/api")


class SitemapEntryDTO(BaseModel):
    id: int
    lastmod: datetime | None


@router.get("/sitemap", response_model=list[SitemapEntryDTO])
async def list_sitemap(
    session: AsyncSession = Depends(get_session),
) -> list[SitemapEntryDTO]:
    rows = (
        await session.execute(
            text(
                "SELECT d.id, COALESCE(d.published_at, d.created_at) AS lastmod "
                f"FROM documents d WHERE {invitado_where('d')} "
                "ORDER BY d.id"
            )
        )
    ).all()
    return [SitemapEntryDTO(id=r.id, lastmod=r.lastmod) for r in rows]
