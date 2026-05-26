"""Database session dep (ADR-0003 §2, §8).

Lives in `core/` so `core/auth` does not need to reach upward into `api/` for
its FastAPI deps. `api/deps.py` re-exports from here for the api layer.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped session; commit on success, rollback on error.

    Commit-at-exit gives `current_user`'s opportunistic refresh `UPDATE` a
    single transaction shared with the route handler — if the handler raises,
    the refresh rolls back with it. Routes that perform their own writes can
    still call `session.commit()` explicitly; the final commit is then a
    no-op.
    """
    sessionmaker = request.app.state.sessionmaker
    async with sessionmaker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
