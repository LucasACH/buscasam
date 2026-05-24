"""Test-data factories for `documents` and `chunks`.

Both helpers pre-allocate ids via `nextval` and route through
`buscasam.fixtures.seed.insert_*`, so schema changes touch one writer.
"""
from __future__ import annotations

from datetime import date

import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.fixtures.corpus import Chunk, Document
from buscasam.fixtures.seed import insert_chunk, insert_document

_DEFAULT_EMBEDDING = np.full(1024, 0.1, dtype=np.float16)


async def make_document(
    session: AsyncSession,
    *,
    visibility: str = "publico",
    publication_status: str = "published",
    titulo: str = "test doc",
    fecha: date = date(2024, 1, 1),
    area_path: str = "escuela_ciencia",
    tipo: str = "paper",
    abstract: str | None = None,
    soft_deleted: bool = False,
    moderation_hidden: bool = False,
) -> int:
    conn = await session.connection()
    new_id = (
        await conn.execute(text("SELECT nextval('documents_id_seq')"))
    ).scalar_one()
    await insert_document(
        conn,
        Document(
            id=new_id,
            visibility=visibility,
            publication_status=publication_status,
            titulo=titulo,
            fecha=fecha,
            area_path=area_path,
            tipo=tipo,
            abstract=abstract,
            soft_deleted=soft_deleted,
            moderation_hidden=moderation_hidden,
        ),
    )
    return new_id


async def make_chunk(
    session: AsyncSession,
    doc_id: int,
    *,
    chunk_seq: int = 0,
    is_headline: bool = False,
    body_text: str = "test body",
    embedding: np.ndarray | None = None,
) -> int:
    conn = await session.connection()
    new_id = (
        await conn.execute(text("SELECT nextval('chunks_id_seq')"))
    ).scalar_one()
    await insert_chunk(
        conn,
        Chunk(
            id=new_id,
            doc_id=doc_id,
            chunk_seq=chunk_seq,
            is_headline=is_headline,
            body_text=body_text,
        ),
        embedding if embedding is not None else _DEFAULT_EMBEDDING,
    )
    return new_id
