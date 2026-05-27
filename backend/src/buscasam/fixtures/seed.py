"""Idempotent loader for the committed fixture corpus.

Also the sole writer of `documents`/`chunks` row SQL — `insert_document` and
`insert_chunk` are reused by `tests/factories.py` so schema changes touch one
place.
"""
from __future__ import annotations

import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from buscasam.fixtures import embeddings as fixture_embeddings
from buscasam.fixtures.corpus import (
    AREAS,
    CHUNKS,
    DOCUMENTS,
    EMBEDDING_MODEL_VERSION,
    Chunk,
    Document,
)


def _halfvec(values: np.ndarray) -> str:
    return "[" + ",".join(f"{float(v):.6f}" for v in values) + "]"


async def insert_document(conn: AsyncConnection, doc: Document) -> None:
    await conn.execute(
        text(
            "INSERT INTO documents (id, visibility, publication_status, titulo, "
            "fecha, area_path, tipo, abstract, soft_deleted_at, moderation_hidden_at) "
            "VALUES (:id, :visibility, :publication_status, :titulo, :fecha, "
            ":area_path, :tipo, :abstract, "
            f"{'now()' if doc.soft_deleted else 'NULL'}, "
            f"{'now()' if doc.moderation_hidden else 'NULL'}) "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {
            "id": doc.id,
            "visibility": doc.visibility,
            "publication_status": doc.publication_status,
            "titulo": doc.titulo,
            "fecha": doc.fecha,
            "area_path": doc.area_path,
            "tipo": doc.tipo,
            "abstract": doc.abstract,
        },
    )


async def insert_chunk(
    conn: AsyncConnection, chunk: Chunk, embedding: np.ndarray
) -> None:
    await conn.execute(
        text(
            "INSERT INTO document_versions "
            "(doc_id, version_no, sha256, original_filename, bytes, mime, "
            " is_current, index_status, extract_pipeline_version) "
            "VALUES (:doc_id, 1, decode(repeat('00', 32), 'hex'), "
            " 'fixture-current', 0, 'application/pdf', true, 'indexed', "
            " 'fixture-current') "
            "ON CONFLICT DO NOTHING"
        ),
        {"doc_id": chunk.doc_id},
    )
    version_id = (
        await conn.execute(
            text(
                "SELECT id FROM document_versions "
                "WHERE doc_id = :doc_id AND is_current"
            ),
            {"doc_id": chunk.doc_id},
        )
    ).scalar_one()
    await conn.execute(
        text(
            "INSERT INTO chunks (id, doc_id, chunk_seq, is_headline, "
            "body_text, embedding, embedding_model_version, version_id, is_current) "
            "VALUES (:id, :doc_id, :seq, :hl, :body, "
            f"'{_halfvec(embedding)}'::halfvec(1024), :mv, :version_id, true) "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {
            "id": chunk.id,
            "doc_id": chunk.doc_id,
            "seq": chunk.chunk_seq,
            "hl": chunk.is_headline,
            "body": chunk.body_text,
            "mv": EMBEDDING_MODEL_VERSION,
            "version_id": version_id,
        },
    )


async def seed(conn: AsyncConnection) -> None:
    embedding_table = fixture_embeddings.load()

    await conn.execute(
        text(
            "INSERT INTO areas (area_path, display_name) VALUES "
            + ",".join(
                f"('{a.area_path}', '{a.display_name.replace(chr(39), chr(39) * 2)}')"
                for a in AREAS
            )
            + " ON CONFLICT (area_path) DO NOTHING"
        )
    )

    for doc in DOCUMENTS:
        await insert_document(conn, doc)

    for c in CHUNKS:
        await insert_chunk(conn, c, fixture_embeddings.lookup(embedding_table, c))

    await conn.execute(
        text("SELECT setval('documents_id_seq', (SELECT max(id) FROM documents))")
    )
    await conn.execute(
        text("SELECT setval('chunks_id_seq', (SELECT max(id) FROM chunks))")
    )
