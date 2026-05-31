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
# core/documents is a package split by capability; the whole subtree is the
# chokepoint, so the exemption is the directory, not a single file.
DOCUMENTS_DIR = SRC_ROOT / "core" / "documents"
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
# hide stamps it, unhide clears it. Same assignment-only match as soft_deleted_at,
# so the read predicates (`moderation_hidden_at IS NULL`) in core/document_access
# are not flagged.
_MODERATION_HIDDEN_WRITE_RE = re.compile(
    r"(SET\b[^;]*?\bmoderation_hidden_at\s*=|INSERT\s+INTO\s+documents\b[^;]*?\bmoderation_hidden_at\b)",
    re.IGNORECASE,
)


def _request_path_python_files(*exempt: Path):
    for p in SRC_ROOT.rglob("*.py"):
        if "__pycache__" in p.parts or "migrations" in p.parts:
            continue
        if any(p == e or e in p.parents for e in exempt):
            continue
        yield p


def test_document_versions_written_only_by_core_documents():
    offenders = [
        p
        for p in _request_path_python_files(DOCUMENTS_DIR, SEED_FILE)
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
        for p in _request_path_python_files(DOCUMENTS_DIR, SEED_FILE)
        if _SOFT_DELETE_WRITE_RE.search(p.read_text(encoding="utf-8"))
    ]
    assert offenders == [], (
        "soft_deleted_at write SQL found outside core/documents: "
        + ", ".join(str(p.relative_to(SRC_ROOT)) for p in offenders)
    )


def test_moderation_hidden_at_written_only_by_core_moderation():
    """Issue #78 / module map §Architecture guard: hide/unhide are the only
    writers of the moderation visibility clock, so the stamp/clear invariant
    cannot drift across modules. Seed is bootstrap, not a request-path writer."""
    offenders = [
        p
        for p in _request_path_python_files(MODERATION_FILE, SEED_FILE)
        if _MODERATION_HIDDEN_WRITE_RE.search(p.read_text(encoding="utf-8"))
    ]
    assert offenders == [], (
        "moderation_hidden_at write SQL found outside core/moderation: "
        + ", ".join(str(p.relative_to(SRC_ROOT)) for p in offenders)
    )
