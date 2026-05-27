"""Architecture guard: only core/blob_store may perform raw blob filesystem ops.

ADR-0006 §3: all application blob reads/writes/deletes go through core/blob_store.
Checks that no other module under src/buscasam/ uses os.rename or
pathlib.Path.write_bytes (the two write-path primitives) against the blob root,
and that the blob root path literal only appears in blob_store.py.
"""
from __future__ import annotations

import ast
import os
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parent.parent.parent / "src" / "buscasam"
BLOB_STORE_FILE = SRC_ROOT / "core" / "blob_store.py"
SETTINGS_FILE = SRC_ROOT / "settings.py"
BLOB_ROOT_LITERAL = "/var/lib/buscasam/blobs"


def _python_files_except_blob_store():
    for p in SRC_ROOT.rglob("*.py"):
        if p != BLOB_STORE_FILE and "__pycache__" not in p.parts:
            yield p


def _python_files_except_blob_root_owners():
    for p in SRC_ROOT.rglob("*.py"):
        if p in (BLOB_STORE_FILE, SETTINGS_FILE):
            continue
        if "__pycache__" in p.parts:
            continue
        yield p


def _ast_names_used(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Name):
            names.add(node.id)
    return names


def test_no_os_rename_outside_blob_store():
    offenders = [
        p for p in _python_files_except_blob_store()
        if "rename" in _ast_names_used(p)
    ]
    assert offenders == [], (
        "os.rename used outside core/blob_store: "
        + ", ".join(str(p.relative_to(SRC_ROOT)) for p in offenders)
    )


def test_no_write_bytes_outside_blob_store():
    offenders = [
        p for p in _python_files_except_blob_store()
        if "write_bytes" in _ast_names_used(p)
    ]
    assert offenders == [], (
        "Path.write_bytes used outside core/blob_store: "
        + ", ".join(str(p.relative_to(SRC_ROOT)) for p in offenders)
    )


def test_blob_root_literal_only_in_blob_root_owners():
    offenders = [
        p for p in _python_files_except_blob_root_owners()
        if BLOB_ROOT_LITERAL in p.read_text()
    ]
    assert offenders == [], (
        f"{BLOB_ROOT_LITERAL!r} referenced outside core/blob_store + settings: "
        + ", ".join(str(p.relative_to(SRC_ROOT)) for p in offenders)
    )
