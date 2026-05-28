"""Maintenance jobs are daily periodic defers coordinated by one advisory lock.

ADR-0008 §9 / module map §core/jobs: `purge_deleted` and `sweep_orphan_blobs`
register as daily Procrastinate periodic tasks on the `default` queue, and both
acquire one shared maintenance advisory lock (the namespace ADR-0009 backups
reuse) so blob deletion cannot race a backup recovery point.
"""
from __future__ import annotations

from sqlalchemy import text

from buscasam.core import jobs


def test_purge_and_sweep_registered_as_daily_periodic_on_default_queue():
    by_name = {
        pt.task.name.rsplit(".", 1)[-1]: pt
        for pt in jobs.app.periodic_registry.periodic_tasks.values()
    }

    for name in ("purge_deleted", "sweep_orphan_blobs"):
        assert name in by_name, f"{name} not registered as periodic"
        pt = by_name[name]
        assert pt.task.queue == "default"
        minute, hour, dom, month, dow = pt.cron.split()
        assert (dom, month, dow) == ("*", "*", "*")
        assert minute != "*" and hour != "*"


async def test_maintenance_lock_blocks_a_second_acquirer(session, engine):
    async with jobs._with_maintenance_lock(session):
        async with engine.connect() as other:
            acquired = (
                await other.execute(
                    text("SELECT pg_try_advisory_xact_lock(:k)"),
                    {"k": jobs._MAINTENANCE_LOCK_KEY},
                )
            ).scalar_one()

    assert acquired is False
