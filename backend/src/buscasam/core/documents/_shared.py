"""Cross-cutting helpers shared across the documents chokepoint submodules:
the PATCH sentinel, the manageable/owner access gates, and the published
version-history projection reused by drafts and detail reads."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.core.document_access import manageable_where

from buscasam.core.documents.exceptions import DocumentNotFound, NotOwner

if TYPE_CHECKING:
    from buscasam.core.auth import UserCtx


_EMBEDDING_MODEL_VERSION = "multilingual-e5-large@v1"


class _Unset:
    """Sentinel distinguishing an absent PATCH field from an explicit null."""


UNSET = _Unset()


async def assert_manageable(
    session: AsyncSession,
    user_ctx: UserCtx,
    doc_id: int,
) -> None:
    where, params = manageable_where("d", user_ctx)
    exists = (
        await session.execute(
            text(f"SELECT 1 FROM documents d WHERE d.id = :doc_id AND ({where})"),
            {"doc_id": doc_id, **params},
        )
    ).scalar_one_or_none()
    if exists is None:
        raise DocumentNotFound


async def _assert_owner(
    session: AsyncSession, user_ctx: UserCtx, doc_id: int
) -> None:
    """Owner-only predicate stricter than manageable_where: accepted coautores
    cannot manage coauthors (ADR-0010 §8, module map §core/documents)."""
    is_owner = (
        await session.execute(
            text(
                "SELECT 1 FROM document_authors "
                "WHERE doc_id = :doc_id AND user_id = :uid AND status = 'owner'"
            ),
            {"doc_id": doc_id, "uid": user_ctx.user_id},
        )
    ).scalar_one_or_none()
    if is_owner is None:
        raise NotOwner


@dataclass(frozen=True)
class DetailVersion:
    n: int  # 1-based row_number ordering, shared with the version-download route
    original_filename: str
    mime: str
    size_bytes: int
    indexed_at: datetime | None
    is_current: bool


@dataclass(frozen=True)
class _PublishedVersion:
    """One row of the published version-history projection (ADR-0011 §4): a
    version that was at some point the public current. Carries `sha_hex` for the
    download lookup on top of the DetailVersion fields the list projections need."""
    n: int
    sha_hex: str
    original_filename: str
    mime: str
    size_bytes: int
    indexed_at: datetime | None
    is_current: bool


async def _published_version_history(
    session: AsyncSession, doc_id: int
) -> list[_PublishedVersion]:
    """Single locality for the published version-history projection (ADR-0011 §4,
    §11). Owns the three rules every consumer agrees on: the `first_published_at
    IS NOT NULL` gate (only previously-public versions), the stable 1-based
    `n = row_number() OVER (ORDER BY id)` ordering (shared with the version-download
    route so the visible list and the n->file mapping cannot drift), and the
    `is_current` marker. Reused by get_draft_state and get_detail (mapped to
    DetailVersion) and by get_manageable_version_file (resolved by n). Access
    gating is the caller's responsibility; this projection does not gate."""
    rows = (
        await session.execute(
            text(
                "SELECT row_number() OVER (ORDER BY id) AS n, "
                "       encode(sha256, 'hex') AS sha, original_filename, mime, "
                "       bytes, indexed_at, is_current "
                "FROM document_versions "
                "WHERE doc_id = :doc_id AND first_published_at IS NOT NULL "
                "ORDER BY id"
            ),
            {"doc_id": doc_id},
        )
    ).mappings().all()
    return [
        _PublishedVersion(
            n=r["n"],
            sha_hex=r["sha"],
            original_filename=r["original_filename"],
            mime=r["mime"],
            size_bytes=r["bytes"],
            indexed_at=r["indexed_at"],
            is_current=r["is_current"],
        )
        for r in rows
    ]


def _to_detail_version(v: _PublishedVersion) -> DetailVersion:
    return DetailVersion(
        n=v.n,
        original_filename=v.original_filename,
        mime=v.mime,
        size_bytes=v.size_bytes,
        indexed_at=v.indexed_at,
        is_current=v.is_current,
    )
