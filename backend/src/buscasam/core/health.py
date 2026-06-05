"""Service-health probes for the status page (GET /api/health).

Probes only what the API process can reach directly: Postgres, the TEI
embeddings server, and the Procrastinate worker fleet (via its heartbeat and
queue tables). The metadata LLM is reported from config rather than pinged — it
is opt-in per document (ADR-0011), so "enabled vs disabled" is the useful
signal, not a live request. nginx and the frontend are not probed here; the
status page loading at all already exercises that chain.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.settings import settings

Status = Literal["ok", "degraded", "down", "disabled"]

# A live worker heartbeats every few seconds (procrastinate default); a fleet
# with no heartbeat inside this window is treated as down.
_WORKER_HEARTBEAT_STALE_S = 30
# The two worker services in the compose stack (compose.yaml).
_WORKER_QUEUES = ("default", "ocr")
_TEI_HEALTH_TIMEOUT_S = 2.0


@dataclass
class ServiceHealth:
    key: str
    name: str
    status: Status
    detail: str | None = None


@dataclass
class HealthReport:
    status: Status
    services: list[ServiceHealth]


async def _check_database(session: AsyncSession) -> ServiceHealth:
    t0 = time.perf_counter()
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        return ServiceHealth("database", "Base de datos", "down", "sin conexión")
    ms = round((time.perf_counter() - t0) * 1000)
    return ServiceHealth("database", "Base de datos", "ok", f"latencia {ms} ms")


async def _check_embeddings(tei: httpx.AsyncClient) -> ServiceHealth:
    t0 = time.perf_counter()
    try:
        r = await tei.get("/health", timeout=_TEI_HEALTH_TIMEOUT_S)
        r.raise_for_status()
    except Exception:
        return ServiceHealth("embeddings", "Embeddings (TEI)", "down", "sin conexión")
    ms = round((time.perf_counter() - t0) * 1000)
    return ServiceHealth("embeddings", "Embeddings (TEI)", "ok", f"latencia {ms} ms")


async def _check_workers(session: AsyncSession) -> ServiceHealth:
    """Liveness from the procrastinate heartbeat table; backlog as context.

    The heartbeat table does not record which queue a worker drains, so this
    reports the fleet-wide live count plus the combined default/ocr backlog.
    Backlog is informational only (an OCR job legitimately sits pending for the
    ~30-min run) — degraded is driven purely by the absence of a live worker.
    """
    alive = (
        await session.execute(
            text(
                "SELECT count(*) FROM procrastinate_workers "
                "WHERE last_heartbeat > now() - make_interval(secs => :s)"
            ),
            {"s": _WORKER_HEARTBEAT_STALE_S},
        )
    ).scalar_one()
    pending = (
        await session.execute(
            text(
                "SELECT count(*) FROM procrastinate_jobs "
                "WHERE status = 'todo' AND queue_name = ANY(:queues)"
            ),
            {"queues": list(_WORKER_QUEUES)},
        )
    ).scalar_one()
    detail = f"{alive} activo(s) · {pending} en cola"
    status: Status = "ok" if alive > 0 else "degraded"
    return ServiceHealth("workers", "Procesamiento", status, detail)


def _check_metadata_llm() -> ServiceHealth:
    if not settings.metadata_llm_enabled:
        return ServiceHealth("metadata_llm", "Metadata LLM", "disabled", "desactivado")
    return ServiceHealth(
        "metadata_llm",
        "Metadata LLM",
        "ok",
        f"proveedor {settings.metadata_llm_provider}",
    )


def _overall(services: list[ServiceHealth]) -> Status:
    statuses = {s.status for s in services}
    if "down" in statuses:
        return "down"
    if "degraded" in statuses:
        return "degraded"
    return "ok"


async def gather_health(session: AsyncSession, tei: httpx.AsyncClient) -> HealthReport:
    services = [
        await _check_database(session),
        await _check_embeddings(tei),
        await _check_workers(session),
        _check_metadata_llm(),
    ]
    return HealthReport(status=_overall(services), services=services)
