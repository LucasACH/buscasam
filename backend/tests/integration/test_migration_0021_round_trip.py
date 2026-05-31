"""0021 upgrade/downgrade is reversible for the chunks trigram index."""

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


def _regclass_exists(url: str, name: str) -> bool:
    eng = create_engine(url)
    try:
        with eng.connect() as conn:
            return (
                conn.execute(
                    text("SELECT to_regclass('public.' || :n)"), {"n": name}
                ).scalar()
                is not None
            )
    finally:
        eng.dispose()


def _extension_exists(url: str, name: str) -> bool:
    eng = create_engine(url)
    try:
        with eng.connect() as conn:
            return (
                conn.execute(
                    text("SELECT 1 FROM pg_extension WHERE extname = :n"), {"n": name}
                ).scalar()
                is not None
            )
    finally:
        eng.dispose()


def test_0021_upgrade_then_downgrade_then_upgrade(isolated_db):
    url = isolated_db
    cfg = _alembic_cfg(url)

    command.upgrade(cfg, "0020")
    assert _regclass_exists(url, "chunks_body_text_trgm") is False

    command.upgrade(cfg, "0021")
    assert _extension_exists(url, "pg_trgm") is True
    assert _regclass_exists(url, "chunks_body_text_trgm") is True

    command.downgrade(cfg, "0020")
    assert _regclass_exists(url, "chunks_body_text_trgm") is False

    command.upgrade(cfg, "0021")
    assert _regclass_exists(url, "chunks_body_text_trgm") is True
