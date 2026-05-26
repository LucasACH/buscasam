"""HTTP surface for document management endpoints."""
from __future__ import annotations

from pydantic import BaseModel
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.api.deps import get_session
from buscasam.core import auth
from buscasam.core.documents import list_own_documents

router = APIRouter(prefix="/api")


class OwnDocDTO(BaseModel):
    id: int
    title: str
    publication_status: str
    visibility: str


@router.get("/me/documents", response_model=list[OwnDocDTO])
async def get_own_documents(
    user_ctx: auth.UserCtx = Depends(auth.require_authenticated),
    session: AsyncSession = Depends(get_session),
) -> list[OwnDocDTO]:
    docs = await list_own_documents(session, user_ctx)
    return [
        OwnDocDTO(
            id=d.id,
            title=d.title,
            publication_status=d.publication_status,
            visibility=d.visibility,
        )
        for d in docs
    ]
