"""Domain chokepoint for all document mutations and queries (ADR-0010 §6, module map §core/documents)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.core.document_access import manageable_where

if TYPE_CHECKING:
    from buscasam.core.auth import UserCtx
    from buscasam.core.blob_store import BlobPutResult


class DocumentNotFound(Exception):
    pass


class InvalidCoauthorId(Exception):
    def __init__(self, ids: set[int]) -> None:
        self.ids = ids


@dataclass(frozen=True)
class OwnDocSummary:
    id: int
    title: str
    publication_status: str
    visibility: str


async def create_draft(
    session: AsyncSession,
    user_ctx: UserCtx,
    *,
    title: str,
    area_path: str,
    document_type: str,
    visibility: str,
    external_authors: list[str],
    coauthor_user_ids: list[int],
) -> int:
    owner_name = (
        await session.execute(
            text("SELECT name FROM users WHERE id = :uid"),
            {"uid": user_ctx.user_id},
        )
    ).scalar_one_or_none() or ""

    doc_id = (
        await session.execute(
            text(
                "INSERT INTO documents (visibility, publication_status, titulo, fecha, area_path, tipo) "
                "VALUES (:visibility, 'draft', :titulo, CURRENT_DATE, :area_path, :tipo) RETURNING id"
            ),
            {
                "visibility": visibility,
                "titulo": title,
                "area_path": area_path,
                "tipo": document_type,
            },
        )
    ).scalar_one()

    await session.execute(
        text(
            "INSERT INTO document_authors (doc_id, user_id, display_name, status) "
            "VALUES (:doc_id, :uid, :name, 'owner')"
        ),
        {"doc_id": doc_id, "uid": user_ctx.user_id, "name": owner_name},
    )

    if coauthor_user_ids:
        valid_ids = set(
            (
                await session.execute(
                    text("SELECT id FROM users WHERE id = ANY(:ids)"),
                    {"ids": coauthor_user_ids},
                )
            )
            .scalars()
            .all()
        )
        missing = set(coauthor_user_ids) - valid_ids
        if missing:
            raise InvalidCoauthorId(missing)

    for coauthor_id in coauthor_user_ids:
        coauthor_name = (
            await session.execute(
                text("SELECT name FROM users WHERE id = :uid"),
                {"uid": coauthor_id},
            )
        ).scalar_one_or_none() or ""
        await session.execute(
            text(
                "INSERT INTO document_authors (doc_id, user_id, display_name, status) "
                "VALUES (:doc_id, :uid, :name, 'pending')"
            ),
            {"doc_id": doc_id, "uid": coauthor_id, "name": coauthor_name},
        )

    for external_name in external_authors:
        await session.execute(
            text(
                "INSERT INTO document_authors (doc_id, user_id, display_name, status) "
                "VALUES (:doc_id, NULL, :name, 'external')"
            ),
            {"doc_id": doc_id, "name": external_name},
        )

    return doc_id


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


async def attach_main_version(
    session: AsyncSession,
    user_ctx: UserCtx,
    doc_id: int,
    blob: BlobPutResult,
    *,
    original_filename: str,
) -> int:
    version_no = (
        await session.execute(
            text(
                "SELECT COALESCE(MAX(version_no), 0) + 1 "
                "FROM document_versions WHERE doc_id = :doc_id"
            ),
            {"doc_id": doc_id},
        )
    ).scalar_one()

    version_id = (
        await session.execute(
            text(
                "INSERT INTO document_versions "
                "(doc_id, version_no, sha256, original_filename, bytes, mime, uploaded_by) "
                "VALUES (:doc_id, :version_no, decode(:sha256, 'hex'), "
                ":filename, :bytes, :mime, :uid) RETURNING id"
            ),
            {
                "doc_id": doc_id,
                "version_no": version_no,
                "sha256": blob.sha256,
                "filename": original_filename,
                "bytes": blob.bytes,
                "mime": blob.sniffed_mime,
                "uid": user_ctx.user_id,
            },
        )
    ).scalar_one()

    return version_id


async def list_own_documents(
    session: AsyncSession, user_ctx: UserCtx
) -> list[OwnDocSummary]:
    where, params = manageable_where("d", user_ctx)
    rows = (
        await session.execute(
            text(
                f"SELECT d.id, d.titulo, d.publication_status, d.visibility "
                f"FROM documents d WHERE {where} ORDER BY d.id"
            ),
            params,
        )
    ).mappings().all()
    return [
        OwnDocSummary(
            id=r["id"],
            title=r["titulo"],
            publication_status=r["publication_status"],
            visibility=r["visibility"],
        )
        for r in rows
    ]
