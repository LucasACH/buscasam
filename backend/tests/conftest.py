import asyncio
import os
import sys
import uuid
from pathlib import Path

# Tests assert the X-Accel-Redirect headers and empty body shipped to nginx;
# force the inline-streaming dev shim off regardless of the developer's .env.
os.environ["BUSCASAM_SERVE_BLOBS_INLINE"] = "0"

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

BACKEND_ROOT = Path(__file__).resolve().parent.parent
ADMIN_URL = os.environ.get(
    "BUSCASAM_TEST_ADMIN_URL",
    "postgresql+psycopg://buscasam:buscasam@localhost:5432/postgres",
)


@pytest.fixture(scope="session")
def event_loop_policy():
    # psycopg async cannot run on Windows' default ProactorEventLoop; the
    # selector loop matches the Linux/CI default. No-op off Windows.
    if sys.platform == "win32":
        return asyncio.WindowsSelectorEventLoopPolicy()
    return asyncio.get_event_loop_policy()


def _create_db(name: str) -> None:
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    admin.dispose()


def _drop_db(name: str) -> None:
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
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


@pytest_asyncio.fixture(scope="session")
async def engine():
    name = f"buscasam_test_{uuid.uuid4().hex[:12]}"
    url = f"{ADMIN_URL.rsplit('/', 1)[0]}/{name}"
    _create_db(name)

    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "src/buscasam/migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    os.environ["BUSCASAM_DATABASE_URL"] = url
    command.upgrade(cfg, "head")

    engine = create_async_engine(url)
    try:
        yield engine
    finally:
        await engine.dispose()
        _drop_db(name)


@pytest_asyncio.fixture
async def session(engine):
    async with engine.connect() as conn:
        await conn.begin()
        async with AsyncSession(
            bind=conn, join_transaction_mode="create_savepoint"
        ) as s:
            yield s
        await conn.rollback()
