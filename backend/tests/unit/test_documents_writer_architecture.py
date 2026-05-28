"""Architecture guard: only core/documents may write document_versions.

ADR-0011 §12 / module map §core/documents: the domain chokepoint is the sole
writer of document_versions. Extends the publication.md rule to cover
replace_main_version + the discarded transition. Schema DDL (migrations) and the
corpus seed loader (fixtures/seed.py) are bootstrap paths, not request-path
writers, and are exempt.
"""
from __future__ import annotations

import re
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parent.parent.parent / "src" / "buscasam"
DOCUMENTS_FILE = SRC_ROOT / "core" / "documents.py"
SEED_FILE = SRC_ROOT / "fixtures" / "seed.py"

_WRITE_RE = re.compile(
    r"(INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+document_versions", re.IGNORECASE
)


def _request_path_python_files():
    for p in SRC_ROOT.rglob("*.py"):
        if "__pycache__" in p.parts or "migrations" in p.parts:
            continue
        if p in (DOCUMENTS_FILE, SEED_FILE):
            continue
        yield p


def test_document_versions_written_only_by_core_documents():
    offenders = [
        p for p in _request_path_python_files() if _WRITE_RE.search(p.read_text())
    ]
    assert offenders == [], (
        "document_versions write SQL found outside core/documents: "
        + ", ".join(str(p.relative_to(SRC_ROOT)) for p in offenders)
    )
