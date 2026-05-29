"""0016 upgrade/downgrade is reversible (document_reports + moderation_actions).

Builds on the test_migration_0014_round_trip.py pattern: stands up an isolated
database, runs migrations through 0015, then verifies the two moderation tables,
the open-report unique partial index, and the status/action CHECKs appear on
upgrade and disappear on downgrade.
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


def _seed_doc_and_user(url: str) -> tuple[int, int]:
    """Insert one document and one user at the 0016 schema; returns their ids."""
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
            user_id = c.execute(
                text(
                    "INSERT INTO users (google_sub, email, hd, role, name) VALUES "
                    "('sub-1', 'r@unsam.edu.ar', 'unsam.edu.ar', 'usuario', 'R') "
                    "RETURNING id"
                )
            ).scalar_one()
        return doc_id, user_id
    finally:
        eng.dispose()


def test_0016_upgrade_then_downgrade_then_upgrade(isolated_db):
    url = isolated_db
    cfg = _alembic_cfg(url)

    command.upgrade(cfg, "0015")
    assert _table_exists(url, "document_reports") is False
    assert _table_exists(url, "moderation_actions") is False

    command.upgrade(cfg, "0016")
    assert _table_exists(url, "document_reports") is True
    assert _table_exists(url, "moderation_actions") is True

    command.downgrade(cfg, "0015")
    assert _table_exists(url, "document_reports") is False
    assert _table_exists(url, "moderation_actions") is False

    command.upgrade(cfg, "0016")
    assert _table_exists(url, "document_reports") is True
    assert _table_exists(url, "moderation_actions") is True


def test_0016_second_open_report_violates_unique_partial_index(isolated_db):
    url = isolated_db
    cfg = _alembic_cfg(url)
    command.upgrade(cfg, "0016")
    doc_id, user_id = _seed_doc_and_user(url)

    eng = create_engine(url)
    try:
        with eng.begin() as c:
            c.execute(
                text(
                    "INSERT INTO document_reports (doc_id, reporter_user_id, reason) "
                    "VALUES (:d, :u, 'spam')"
                ),
                {"d": doc_id, "u": user_id},
            )
        with pytest.raises(IntegrityError, match="document_reports_open_uniq"):
            with eng.begin() as c:
                c.execute(
                    text(
                        "INSERT INTO document_reports (doc_id, reporter_user_id, reason) "
                        "VALUES (:d, :u, 'plagio')"
                    ),
                    {"d": doc_id, "u": user_id},
                )
    finally:
        eng.dispose()


def test_0016_resolved_and_open_report_coexist(isolated_db):
    url = isolated_db
    cfg = _alembic_cfg(url)
    command.upgrade(cfg, "0016")
    doc_id, user_id = _seed_doc_and_user(url)

    eng = create_engine(url)
    try:
        with eng.begin() as c:
            c.execute(
                text(
                    "INSERT INTO document_reports "
                    "(doc_id, reporter_user_id, reason, status) "
                    "VALUES (:d, :u, 'spam', 'resolved')"
                ),
                {"d": doc_id, "u": user_id},
            )
            c.execute(
                text(
                    "INSERT INTO document_reports "
                    "(doc_id, reporter_user_id, reason, status) "
                    "VALUES (:d, :u, 'plagio', 'open')"
                ),
                {"d": doc_id, "u": user_id},
            )
    finally:
        eng.dispose()


def test_0016_status_check_rejects_unknown_value(isolated_db):
    url = isolated_db
    cfg = _alembic_cfg(url)
    command.upgrade(cfg, "0016")
    doc_id, user_id = _seed_doc_and_user(url)

    eng = create_engine(url)
    try:
        with pytest.raises(IntegrityError, match="document_reports_status_check"):
            with eng.begin() as c:
                c.execute(
                    text(
                        "INSERT INTO document_reports "
                        "(doc_id, reporter_user_id, reason, status) "
                        "VALUES (:d, :u, 'spam', 'archived')"
                    ),
                    {"d": doc_id, "u": user_id},
                )
    finally:
        eng.dispose()


def test_0016_action_check_rejects_unknown_value(isolated_db):
    url = isolated_db
    cfg = _alembic_cfg(url)
    command.upgrade(cfg, "0016")
    doc_id, user_id = _seed_doc_and_user(url)

    eng = create_engine(url)
    try:
        with eng.begin() as c:
            report_id = c.execute(
                text(
                    "INSERT INTO document_reports (doc_id, reporter_user_id, reason) "
                    "VALUES (:d, :u, 'spam') RETURNING id"
                ),
                {"d": doc_id, "u": user_id},
            ).scalar_one()
        # Valid action accepted.
        with eng.begin() as c:
            c.execute(
                text(
                    "INSERT INTO moderation_actions "
                    "(report_id, docente_user_id, action, reason) "
                    "VALUES (:r, :u, 'hide', 'inapropiado')"
                ),
                {"r": report_id, "u": user_id},
            )
        with pytest.raises(IntegrityError, match="moderation_actions_action_check"):
            with eng.begin() as c:
                c.execute(
                    text(
                        "INSERT INTO moderation_actions "
                        "(report_id, docente_user_id, action) "
                        "VALUES (:r, :u, 'delete')"
                    ),
                    {"r": report_id, "u": user_id},
                )
    finally:
        eng.dispose()
