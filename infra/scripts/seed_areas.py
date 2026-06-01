"""One-off: load the UNSAM áreas reference tree into the prod `areas` table.

Idempotent. Mirrors the áreas portion of `buscasam.fixtures.seed.seed`
(reconcile managed escuela roots, then upsert) without touching the fixture
documents/chunks. Run inside the api container:

    docker exec -i infra-api-1 python - < infra/scripts/seed_areas.py
"""

from __future__ import annotations

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from buscasam.fixtures import unsam_areas
from buscasam.settings import settings


async def main() -> None:
    rows = unsam_areas.load()
    roots = [r["area_path"] for r in rows if "." not in r["area_path"]]
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        before = (await conn.execute(text("SELECT count(*) FROM areas"))).scalar_one()
        await conn.execute(
            text("DELETE FROM areas WHERE area_path <@ ANY(CAST(:roots AS ltree[]))"),
            {"roots": roots},
        )
        await conn.execute(
            text(
                "INSERT INTO areas (area_path, display_name) "
                "VALUES (:area_path, :display_name) "
                "ON CONFLICT (area_path) DO NOTHING"
            ),
            rows,
        )
        after = (await conn.execute(text("SELECT count(*) FROM areas"))).scalar_one()
    await engine.dispose()
    print(f"areas seed ok: loaded {len(rows)} rows; count {before} -> {after}")


asyncio.run(main())
