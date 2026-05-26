"""Domain chokepoint for all document mutations and queries (ADR-0010 §6, module map §core/documents)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.core.document_access import manageable_where

if TYPE_CHECKING:
    from buscasam.core.auth import UserCtx
    from buscasam.core.blob_store import BlobPutResult
    from buscasam.core.chunk import Chunk
    from buscasam.core.extract import IndexableMetadata


_EMBEDDING_MODEL_VERSION = "multilingual-e5-large@v1"


def _halfvec_literal(values: np.ndarray) -> str:
    return "[" + ",".join(f"{float(v):.6f}" for v in values) + "]"


@dataclass(frozen=True)
class CandidateVersion:
    version_id: int
    doc_id: int
    sha256: str
    mime: str
    title: str
    owner_user_id: int | None


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

    coauthor_names: dict[int, str] = {}
    if coauthor_user_ids:
        rows = (
            await session.execute(
                text("SELECT id, name FROM users WHERE id = ANY(:ids)"),
                {"ids": coauthor_user_ids},
            )
        ).mappings().all()
        coauthor_names = {r["id"]: r["name"] for r in rows}
        missing = set(coauthor_user_ids) - coauthor_names.keys()
        if missing:
            raise InvalidCoauthorId(missing)

    for coauthor_id in coauthor_user_ids:
        await session.execute(
            text(
                "INSERT INTO document_authors (doc_id, user_id, display_name, status) "
                "VALUES (:doc_id, :uid, :name, 'pending')"
            ),
            {"doc_id": doc_id, "uid": coauthor_id, "name": coauthor_names[coauthor_id]},
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

    # ADR-0008 §1: defer index_document through the active transaction so the
    # version row + the job row commit together.
    from buscasam.core import jobs

    await jobs.enqueue_index_document(session, version_id)

    return version_id


async def load_candidate(
    session: AsyncSession, version_id: int
) -> CandidateVersion:
    row = (
        await session.execute(
            text(
                "SELECT v.id, v.doc_id, encode(v.sha256, 'hex') AS sha, v.mime, "
                "       d.titulo, "
                "       (SELECT a.user_id FROM document_authors a "
                "         WHERE a.doc_id = v.doc_id AND a.status = 'owner' LIMIT 1) "
                "         AS owner_user_id "
                "FROM document_versions v JOIN documents d ON d.id = v.doc_id "
                "WHERE v.id = :id"
            ),
            {"id": version_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise DocumentNotFound
    return CandidateVersion(
        version_id=row["id"],
        doc_id=row["doc_id"],
        sha256=row["sha"],
        mime=row["mime"],
        title=row["titulo"],
        owner_user_id=row["owner_user_id"],
    )


async def write_indexed_candidate(
    session: AsyncSession,
    version_id: int,
    *,
    body: list["Chunk"],
    headline: "Chunk",
    embeds: list[np.ndarray],
    meta: "IndexableMetadata",
    headline_fingerprint: str,
) -> None:
    doc_id = (
        await session.execute(
            text("SELECT doc_id FROM document_versions WHERE id = :id"),
            {"id": version_id},
        )
    ).scalar_one()

    all_chunks = [headline, *body]
    for c, emb in zip(all_chunks, embeds):
        await session.execute(
            text(
                "INSERT INTO chunks (doc_id, chunk_seq, is_headline, body_text, "
                "  embedding, embedding_model_version, version_id, is_current) "
                f"VALUES (:doc_id, :seq, :hl, :body, '{_halfvec_literal(emb)}'::halfvec(1024), "
                ":mv, :vid, false)"
            ),
            {
                "doc_id": doc_id,
                "seq": c.chunk_seq,
                "hl": c.is_headline,
                "body": c.body_text,
                "mv": _EMBEDDING_MODEL_VERSION,
                "vid": version_id,
            },
        )

    await session.execute(
        text(
            "UPDATE document_versions SET "
            "  index_status = 'indexed', "
            "  staged_abstract = :abstract, "
            "  staged_keywords = :keywords, "
            "  staged_fecha = :fecha, "
            "  headline_fingerprint = :fp, "
            "  indexed_at = now() "
            "WHERE id = :id"
        ),
        {
            "abstract": meta.abstract,
            "keywords": meta.keywords,
            "fecha": meta.fecha,
            "fp": headline_fingerprint,
            "id": version_id,
        },
    )


async def write_headline(
    session: AsyncSession,
    version_id: int,
    headline: "Chunk",
    embed: np.ndarray,
    headline_fingerprint: str,
) -> None:
    doc_id = (
        await session.execute(
            text("SELECT doc_id FROM document_versions WHERE id = :id"),
            {"id": version_id},
        )
    ).scalar_one()

    await session.execute(
        text(
            "DELETE FROM chunks WHERE version_id = :vid AND is_headline"
        ),
        {"vid": version_id},
    )
    await session.execute(
        text(
            "INSERT INTO chunks (doc_id, chunk_seq, is_headline, body_text, "
            "  embedding, embedding_model_version, version_id, is_current) "
            f"VALUES (:doc_id, 0, true, :body, '{_halfvec_literal(embed)}'::halfvec(1024), "
            ":mv, :vid, false)"
        ),
        {
            "doc_id": doc_id,
            "body": headline.body_text,
            "mv": _EMBEDDING_MODEL_VERSION,
            "vid": version_id,
        },
    )
    await session.execute(
        text(
            "UPDATE document_versions SET headline_fingerprint = :fp WHERE id = :id"
        ),
        {"fp": headline_fingerprint, "id": version_id},
    )


async def mark_failed(
    session: AsyncSession, version_id: int, error: str
) -> None:
    """ADR-0010 §9: insert a unique-keyed processing_failed notification."""
    cv = await load_candidate(session, version_id)
    await session.execute(
        text(
            "UPDATE document_versions SET index_status = 'failed', "
            "  index_error = :err WHERE id = :id"
        ),
        {"err": error, "id": version_id},
    )
    if cv.owner_user_id is None:
        return
    await session.execute(
        text(
            "INSERT INTO notifications (user_id, event_key, kind, payload_json) "
            "VALUES (:uid, :ek, 'processing_failed', "
            "        jsonb_build_object('doc_id', cast(:doc_id as bigint), "
            "                           'version_id', cast(:vid as bigint), "
            "                           'error', cast(:err as text))) "
            "ON CONFLICT (user_id, event_key) DO NOTHING"
        ),
        {
            "uid": cv.owner_user_id,
            "ek": f"processing_failed:{version_id}",
            "doc_id": cv.doc_id,
            "vid": version_id,
            "err": error,
        },
    )


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
