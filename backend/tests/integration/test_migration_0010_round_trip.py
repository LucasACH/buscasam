"""0010 upgrade/downgrade is reversible (document_versions, document_attachments, chunks extension).

Runs against an isolated database; verifies:
- document_versions and document_attachments tables appear/disappear on up/down.
- chunks gains version_id and is_current columns.
- Backfill sets is_current=true on pre-existing chunks and links them to a
  synthesized document_versions row.
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


def _seed_document_and_chunk(url: str) -> tuple[int, int]:
    """Insert one document + one chunk at 0009 schema; return (doc_id, chunk_id)."""
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
            chunk_id = c.execute(
                text(
                    "INSERT INTO chunks (doc_id, chunk_seq, is_headline, body_text, "
                    "embedding, embedding_model_version) VALUES "
                    "(:doc_id, 0, false, 'body', "
                    "'[" + ",".join(["0.1"] * 1024) + "]'::halfvec(1024), 'test') "
                    "RETURNING id"
                ),
                {"doc_id": doc_id},
            ).scalar_one()
        return doc_id, chunk_id
    finally:
        eng.dispose()


def _chunk_row(url: str, chunk_id: int) -> dict:
    eng = create_engine(url)
    try:
        with eng.connect() as c:
            return dict(
                c.execute(
                    text("SELECT version_id, is_current FROM chunks WHERE id = :id"),
                    {"id": chunk_id},
                ).mappings().one()
            )
    finally:
        eng.dispose()


def test_0010_upgrade_then_downgrade_then_upgrade(isolated_db):
    url = isolated_db
    cfg = _alembic_cfg(url)

    command.upgrade(cfg, "0009")
    doc_id, chunk_id = _seed_document_and_chunk(url)

    command.upgrade(cfg, "0010")

    assert _table_exists(url, "document_versions") is True
    assert _table_exists(url, "document_attachments") is True
    assert _column_exists(url, "chunks", "version_id") is True
    assert _column_exists(url, "chunks", "is_current") is True

    row = _chunk_row(url, chunk_id)
    assert row["is_current"] is True
    assert row["version_id"] is not None

    command.downgrade(cfg, "0009")
    assert _table_exists(url, "document_versions") is False
    assert _table_exists(url, "document_attachments") is False
    assert _column_exists(url, "chunks", "version_id") is False
    assert _column_exists(url, "chunks", "is_current") is False

    command.upgrade(cfg, "0010")
    assert _table_exists(url, "document_versions") is True


def test_0013_backfills_unversioned_chunks_and_allows_replacement_sequences(isolated_db):
    url = isolated_db
    cfg = _alembic_cfg(url)

    command.upgrade(cfg, "0010")
    doc_id, chunk_id = _seed_document_and_chunk(url)

    command.upgrade(cfg, "0013")

    row = _chunk_row(url, chunk_id)
    assert row["version_id"] is not None
    assert row["is_current"] is True

    eng = create_engine(url)
    try:
        with eng.begin() as c:
            assert c.execute(
                text(
                    "SELECT is_nullable FROM information_schema.columns "
                    "WHERE table_name = 'chunks' AND column_name = 'version_id'"
                )
            ).scalar_one() == "NO"
            replacement_id = c.execute(
                text(
                    "INSERT INTO document_versions "
                    "(doc_id, version_no, sha256, original_filename, bytes, mime, "
                    " index_status) VALUES "
                    "(:doc, 2, decode(repeat('02', 32), 'hex'), 'replacement.pdf', "
                    " 1, 'application/pdf', 'indexed') RETURNING id"
                ),
                {"doc": doc_id},
            ).scalar_one()
            c.execute(
                text(
                    "INSERT INTO chunks "
                    "(doc_id, chunk_seq, is_headline, body_text, "
                    " embedding_model_version, version_id, is_current) VALUES "
                    "(:doc, 0, false, 'replacement', 'test', :version, false)"
                ),
                {"doc": doc_id, "version": replacement_id},
            )
            assert c.execute(
                text("SELECT count(*) FROM chunks WHERE doc_id = :doc"),
                {"doc": doc_id},
            ).scalar_one() == 2
    finally:
        eng.dispose()
