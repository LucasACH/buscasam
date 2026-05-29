"""Architecture guard: only core/notifications may produce notification rows.

Goal of the consolidation (module map §core/notifications): event-key format,
kind, payload shape, and the ON CONFLICT idempotency stop drifting across the
several producers (coauthor fan-out, indexing/headline failure, hide/unhide) by
having exactly one writer of `INSERT INTO notifications`. Read-state mutations
(`UPDATE … read_at`, `DELETE FROM notifications` on revoke) are consumer-side
and intentionally not matched — only production inserts are guarded.
"""
from __future__ import annotations

import re
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parent.parent.parent / "src" / "buscasam"
NOTIFICATIONS_FILE = SRC_ROOT / "core" / "notifications.py"

_INSERT_RE = re.compile(r"INSERT\s+INTO\s+notifications\b", re.IGNORECASE)


def _request_path_python_files(*exempt: Path):
    for p in SRC_ROOT.rglob("*.py"):
        if "__pycache__" in p.parts or "migrations" in p.parts:
            continue
        if p in exempt:
            continue
        yield p


def test_notifications_inserted_only_by_core_notifications():
    offenders = [
        p
        for p in _request_path_python_files(NOTIFICATIONS_FILE)
        if _INSERT_RE.search(p.read_text(encoding="utf-8"))
    ]
    assert offenders == [], (
        "INSERT INTO notifications found outside core/notifications: "
        + ", ".join(str(p.relative_to(SRC_ROOT)) for p in offenders)
    )
