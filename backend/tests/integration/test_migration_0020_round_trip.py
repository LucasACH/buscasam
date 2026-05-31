"""0020 upgrade/downgrade is reversible (document_reads table + rolling-window
index), and a hard document delete cascades its reads.

Follows the test_migration_0014_round_trip.py pattern: stands up an isolated
database, runs migrations through 0019, then verifies the table and index appear
on upgrade and disappear on downgrade, and that ON DELETE CASCADE drops reads.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

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


def _table_exists(url: str, table: str) -> bool:
    eng = create_engine(url)
    try:
        with eng.connect() as c:
            return (
                c.execute(
                    text("SELECT to_regclass('public.' || :t)"), {"t": table}
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


def test_0020_upgrade_then_downgrade_then_upgrade(isolated_db):
    url = isolated_db
    cfg = _alembic_cfg(url)

    command.upgrade(cfg, "0019")
    assert _table_exists(url, "document_reads") is False

    command.upgrade(cfg, "0020")
    assert _table_exists(url, "document_reads") is True
    assert _index_exists(url, "document_reads_day_doc") is True

    command.downgrade(cfg, "0019")
    assert _table_exists(url, "document_reads") is False

    command.upgrade(cfg, "0020")
    assert _table_exists(url, "document_reads") is True


def test_0020_read_cascades_on_document_delete(isolated_db):
    url = isolated_db
    cfg = _alembic_cfg(url)
    command.upgrade(cfg, "0020")

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
                    "INSERT INTO document_reads (doc_id, reader_key, read_day) "
                    "VALUES (:d, 'u:1', CURRENT_DATE)"
                ),
                {"d": doc_id},
            )
        with eng.begin() as c:
            c.execute(text("DELETE FROM documents WHERE id = :d"), {"d": doc_id})
            remaining = c.execute(
                text("SELECT count(*) FROM document_reads WHERE doc_id = :d"),
                {"d": doc_id},
            ).scalar_one()
            assert remaining == 0
    finally:
        eng.dispose()
