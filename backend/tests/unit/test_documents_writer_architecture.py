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
MODERATION_FILE = SRC_ROOT / "core" / "moderation.py"
SEED_FILE = SRC_ROOT / "fixtures" / "seed.py"

_WRITE_RE = re.compile(
    r"(INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+document_versions", re.IGNORECASE
)

# soft_deleted_at is a column, not a table: a write is an UPDATE assignment
# (SET clause containing `soft_deleted_at =`, in any column position) or the
# bootstrap INSERT into documents listing it. The read predicates
# (`soft_deleted_at IS NULL`/`IS NOT NULL`) and purge's `soft_deleted_at <`
# comparison are not matched, since the assignment requires `=`.
_SOFT_DELETE_WRITE_RE = re.compile(
    r"(SET\b[^;]*?\bsoft_deleted_at\s*=|INSERT\s+INTO\s+documents\b[^;]*?\bsoft_deleted_at\b)",
    re.IGNORECASE,
)


# moderation_hidden_at is a column with its own sole writer (core/moderation):
# the SET assignment or the bootstrap INSERT into documents. The read predicates
# (`moderation_hidden_at IS NULL`) in core/document_access are not matched.
_MODERATION_HIDDEN_WRITE_RE = re.compile(
    r"(SET\b[^;]*?\bmoderation_hidden_at\s*=|INSERT\s+INTO\s+documents\b[^;]*?\bmoderation_hidden_at\b)",
    re.IGNORECASE,
)


def _request_path_python_files(*, exempt=(DOCUMENTS_FILE, SEED_FILE)):
    for p in SRC_ROOT.rglob("*.py"):
        if "__pycache__" in p.parts or "migrations" in p.parts:
            continue
        if p in exempt:
            continue
        yield p


def test_document_versions_written_only_by_core_documents():
    offenders = [
        p
        for p in _request_path_python_files()
        if _WRITE_RE.search(p.read_text(encoding="utf-8"))
    ]
    assert offenders == [], (
        "document_versions write SQL found outside core/documents: "
        + ", ".join(str(p.relative_to(SRC_ROOT)) for p in offenders)
    )


def test_soft_deleted_at_written_only_by_core_documents():
    """Story 36 / module map §core/documents: the deletion clock has a single
    writer, so the stamp-once and owner-only rules cannot drift."""
    offenders = [
        p
        for p in _request_path_python_files()
        if _SOFT_DELETE_WRITE_RE.search(p.read_text(encoding="utf-8"))
    ]
    assert offenders == [], (
        "soft_deleted_at write SQL found outside core/documents: "
        + ", ".join(str(p.relative_to(SRC_ROOT)) for p in offenders)
    )


def test_moderation_hidden_at_written_only_by_core_moderation():
    """Module map §Architecture guard: hide/unhide are the single writer of
    documents.moderation_hidden_at, so the hide/unhide invariant cannot drift
    across modules. Seed is a bootstrap path (exempt); core/documents is not the
    writer here and must not assign it."""
    offenders = [
        p
        for p in _request_path_python_files(exempt=(MODERATION_FILE, SEED_FILE))
        if _MODERATION_HIDDEN_WRITE_RE.search(p.read_text(encoding="utf-8"))
    ]
    assert offenders == [], (
        "moderation_hidden_at write SQL found outside core/moderation: "
        + ", ".join(str(p.relative_to(SRC_ROOT)) for p in offenders)
    )
