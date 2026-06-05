"""GET /api/health — service status for the público status page."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.api.deps import get_session, get_tei_client
from buscasam.core import health

router = APIRouter(prefix="/api")


class ServiceHealthDTO(BaseModel):
    key: str
    name: str
    status: str
    detail: str | None = None


class HealthDTO(BaseModel):
    status: str
    services: list[ServiceHealthDTO]


@router.get("/health", response_model=HealthDTO)
async def get_health(
    session: AsyncSession = Depends(get_session),
    tei: httpx.AsyncClient = Depends(get_tei_client),
) -> HealthDTO:
    report = await health.gather_health(session, tei)
    return HealthDTO(
        status=report.status,
        services=[ServiceHealthDTO(**vars(s)) for s in report.services],
    )
