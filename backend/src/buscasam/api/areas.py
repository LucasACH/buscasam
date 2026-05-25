"""GET /api/areas — áreas reference tree for the cascader."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.api.deps import get_session

router = APIRouter(prefix="/api")


class AreaDTO(BaseModel):
    area_path: str
    display_name: str


@router.get("/areas", response_model=list[AreaDTO])
async def list_areas(session: AsyncSession = Depends(get_session)) -> list[AreaDTO]:
    rows = (
        await session.execute(
            text("SELECT area_path::text AS area_path, display_name FROM areas ORDER BY area_path")
        )
    ).all()
    return [AreaDTO(area_path=r.area_path, display_name=r.display_name) for r in rows]
