"""Architecture guard: only core/jobs may import procrastinate.

ADR-0008 §3 / module map §core/jobs: feature code imports the typed enqueue
helpers, not procrastinate. Concentrating task definitions, queueing locks,
and retry policies in one module is what makes the async edge auditable.
"""
from __future__ import annotations

import ast
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parent.parent.parent / "src" / "buscasam"
JOBS_FILE = SRC_ROOT / "core" / "jobs.py"


def _python_files_except_jobs():
    for p in SRC_ROOT.rglob("*.py"):
        if p != JOBS_FILE and "__pycache__" not in p.parts:
            yield p


def _imports_procrastinate(path: Path) -> bool:
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "procrastinate" or alias.name.startswith("procrastinate."):
                    return True
        elif isinstance(node, ast.ImportFrom):
            if node.module == "procrastinate" or (
                node.module and node.module.startswith("procrastinate.")
            ):
                return True
    return False


def test_no_procrastinate_import_outside_core_jobs():
    offenders = [p for p in _python_files_except_jobs() if _imports_procrastinate(p)]
    assert offenders == [], (
        "procrastinate imported outside core/jobs: "
        + ", ".join(str(p.relative_to(SRC_ROOT)) for p in offenders)
    )
