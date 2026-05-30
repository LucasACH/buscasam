"""One backup recovery point (ADR-0009 §11).

Holds the same Postgres advisory lock as blob GC (`_MAINTENANCE_LOCK_KEY`) so a
`pg_dump` never references a blob that GC deletes before the paired blob rsync.
Writes the completion marker only after both the DB dump and the blob snapshot
succeed, then rotates recovery points older than `BACKUP_RETENTION_DAYS`.

Invoked once per day by `scripts/backup_loop.sh` inside the `backup` container.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg

from buscasam.core.jobs import _MAINTENANCE_LOCK_KEY
from buscasam.settings import settings

BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", "/backup/buscasam"))
RETENTION_DAYS = int(os.environ.get("BACKUP_RETENTION_DAYS", "14"))
MARKER = "COMPLETE"


def _libpq_dsn() -> str:
    # settings.database_url is the SQLAlchemy form (postgresql+psycopg://…);
    # pg_dump and libpq want the bare scheme.
    return settings.database_url.replace("postgresql+psycopg://", "postgresql://", 1)


def _latest_complete(recovery: Path) -> Path | None:
    candidates = sorted(
        (p for p in recovery.glob("*") if (p / MARKER).exists()),
        key=lambda p: p.name,
    )
    return candidates[-1] if candidates else None


def _rotate(recovery: Path) -> None:
    cutoff = datetime.now(timezone.utc).timestamp() - RETENTION_DAYS * 86400
    for p in recovery.glob("*"):
        if (p / MARKER).exists() and p.stat().st_mtime < cutoff:
            shutil.rmtree(p, ignore_errors=True)


def main() -> int:
    recovery = BACKUP_DIR / "recovery"
    recovery.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = recovery / ts
    blobs_dest = dest / "blobs"
    blobs_dest.mkdir(parents=True, exist_ok=True)
    prior = _latest_complete(recovery)

    dsn = _libpq_dsn()
    with psycopg.connect(dsn) as conn:
        # Session-level lock held for the whole recovery point; auto-released on close.
        conn.execute("SELECT pg_advisory_lock(%s)", (_MAINTENANCE_LOCK_KEY,))

        subprocess.run(
            ["pg_dump", "-Fc", "--dbname", dsn, "--file", str(dest / "db.dump")],
            check=True,
        )

        rsync = ["rsync", "-a", "--delete"]
        if prior is not None:
            rsync += ["--link-dest", str(prior / "blobs") + "/"]
        rsync += [str(settings.blob_root) + "/", str(blobs_dest) + "/"]
        subprocess.run(rsync, check=True)

    (dest / MARKER).write_text(ts + "\n")
    _rotate(recovery)
    print(f"backup complete: {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
