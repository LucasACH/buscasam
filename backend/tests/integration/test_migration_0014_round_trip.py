"""0014 upgrade/downgrade is reversible (document_versions.first_published_at +
partial unique index + 'discarded' index_status value).

Builds on the test_migration_0010_round_trip.py pattern: stands up an isolated
database, runs migrations through 0013 to seed prior state, then verifies the
0014 column, index, and CHECK constraint appear on upgrade and disappear on
downgrade. Also verifies the backfill stamps first_published_at on pre-existing
is_current=true rows.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
ADMIN_URL = os.environ.get(
    "BUSCASAM_TEST_ADMIN_URL",
    "postgresql+psycopg://buscasam:buscasam@localhost:5432/postgres",
)


def _alembic_cfg(url: str) -> Config:
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option(
        "script_location", str(BACKEND_ROOT / "src/buscasam/migrations")
    )
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


@pytest.fixture
def isolated_db():
    name = f"buscasam_mig_{uuid.uuid4().hex[:12]}"
    url = f"{ADMIN_URL.rsplit('/', 1)[0]}/{name}"
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        yield url
    finally:
        with admin.connect() as conn:
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :n AND pid <> pg_backend_pid()"
                ),
                {"n": name},
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        admin.dispose()


def _column_exists(url: str, table: str, column: str) -> bool:
    eng = create_engine(url)
    try:
        with eng.connect() as c:
            return (
                c.execute(
                    text(
                        "SELECT 1 FROM information_schema.columns "
                        "WHERE table_name = :t AND column_name = :c"
                    ),
                    {"t": table, "c": column},
                ).scalar()
                is not None
            )
    finally:
        eng.dispose()


def _index_exists(url: str, index: str) -> bool:
    eng = create_engine(url)
    try:
        with eng.connect() as c:
            return (
                c.execute(
                    text("SELECT to_regclass('public.' || :i)"), {"i": index}
                ).scalar()
                is not None
            )
    finally:
        eng.dispose()


def _seed_published_document(url: str) -> int:
    """Insert one document with an is_current=true version, at the 0013 schema.
    Returns the version id."""
    eng = create_engine(url)
    try:
        with eng.begin() as c:
            doc_id = c.execute(
                text(
                    "INSERT INTO documents (visibility, publication_status, titulo, "
                    "fecha, area_path, tipo) VALUES "
                    "('publico', 'published', 'Test', '2024-01-01', "
                    "'escuela_ciencia', 'paper') RETURNING id"
                )
            ).scalar_one()
            version_id = c.execute(
                text(
                    "INSERT INTO document_versions "
                    "(doc_id, version_no, sha256, original_filename, bytes, mime, "
                    " index_status, is_current) VALUES "
                    "(:doc, 1, decode(repeat('00', 32), 'hex'), 'f.pdf', 1, "
                    " 'application/pdf', 'indexed', true) RETURNING id"
                ),
                {"doc": doc_id},
            ).scalar_one()
        return version_id
    finally:
        eng.dispose()


def test_0014_upgrade_then_downgrade_then_upgrade(isolated_db):
    url = isolated_db
    cfg = _alembic_cfg(url)

    command.upgrade(cfg, "0013")
    version_id = _seed_published_document(url)

    command.upgrade(cfg, "0014")

    assert _column_exists(url, "document_versions", "first_published_at") is True
    assert _index_exists(url, "document_versions_one_candidate") is True

    # Backfill: is_current=true rows get first_published_at = uploaded_at.
    eng = create_engine(url)
    try:
        with eng.connect() as c:
            row = c.execute(
                text(
                    "SELECT first_published_at, uploaded_at "
                    "FROM document_versions WHERE id = :id"
                ),
                {"id": version_id},
            ).mappings().one()
            assert row["first_published_at"] is not None
            assert row["first_published_at"] == row["uploaded_at"]
    finally:
        eng.dispose()

    command.downgrade(cfg, "0013")
    assert _column_exists(url, "document_versions", "first_published_at") is False
    assert _index_exists(url, "document_versions_one_candidate") is False

    command.upgrade(cfg, "0014")
    assert _column_exists(url, "document_versions", "first_published_at") is True
    assert _index_exists(url, "document_versions_one_candidate") is True


def test_0014_admits_discarded_index_status_value(isolated_db):
    url = isolated_db
    cfg = _alembic_cfg(url)

    command.upgrade(cfg, "0014")

    eng = create_engine(url)
    try:
        with eng.begin() as c:
            doc_id = c.execute(
                text(
                    "INSERT INTO documents (visibility, publication_status, titulo, "
                    "fecha, area_path, tipo) VALUES "
                    "('publico', 'published', 'T', '2024-01-01', "
                    "'escuela_ciencia', 'paper') RETURNING id"
                )
            ).scalar_one()
            c.execute(
                text(
                    "INSERT INTO document_versions "
                    "(doc_id, version_no, sha256, original_filename, bytes, mime, "
                    " index_status, is_current) VALUES "
                    "(:doc, 1, decode(repeat('00', 32), 'hex'), 'f.pdf', 1, "
                    " 'application/pdf', 'discarded', false)"
                ),
                {"doc": doc_id},
            )
    finally:
        eng.dispose()


def test_0014_partial_unique_blocks_two_non_discarded_candidates(isolated_db):
    url = isolated_db
    cfg = _alembic_cfg(url)

    command.upgrade(cfg, "0014")

    eng = create_engine(url)
    try:
        with eng.begin() as c:
            doc_id = c.execute(
                text(
                    "INSERT INTO documents (visibility, publication_status, titulo, "
                    "fecha, area_path, tipo) VALUES "
                    "('publico', 'published', 'T', '2024-01-01', "
                    "'escuela_ciencia', 'paper') RETURNING id"
                )
            ).scalar_one()
            # First candidate: ok.
            c.execute(
                text(
                    "INSERT INTO document_versions "
                    "(doc_id, version_no, sha256, original_filename, bytes, mime, "
                    " index_status, is_current) VALUES "
                    "(:doc, 1, decode(repeat('00', 32), 'hex'), 'a.pdf', 1, "
                    " 'application/pdf', 'pending', false)"
                ),
                {"doc": doc_id},
            )
        # Second non-discarded candidate on same doc: must fail.
        with pytest.raises(IntegrityError, match="document_versions_one_candidate"):
            with eng.begin() as c:
                c.execute(
                    text(
                        "INSERT INTO document_versions "
                        "(doc_id, version_no, sha256, original_filename, bytes, mime, "
                        " index_status, is_current) VALUES "
                        "(:doc, 2, decode(repeat('01', 32), 'hex'), 'b.pdf', 1, "
                        " 'application/pdf', 'processing', false)"
                    ),
                    {"doc": doc_id},
                )
        # A discarded peer is allowed alongside the original candidate.
        with eng.begin() as c:
            c.execute(
                text(
                    "INSERT INTO document_versions "
                    "(doc_id, version_no, sha256, original_filename, bytes, mime, "
                    " index_status, is_current) VALUES "
                    "(:doc, 3, decode(repeat('02', 32), 'hex'), 'c.pdf', 1, "
                    " 'application/pdf', 'discarded', false)"
                ),
                {"doc": doc_id},
            )
    finally:
        eng.dispose()
