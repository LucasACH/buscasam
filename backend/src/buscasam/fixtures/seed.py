"""Idempotent loader for the committed fixture corpus."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from buscasam.fixtures.corpus import (
    AREAS,
    CHUNKS,
    DOCUMENTS,
    EMBEDDING_MODEL_VERSION,
)

EMBEDDINGS_FILE = Path(__file__).parent / "embeddings.npy"


def _load_embeddings() -> np.ndarray:
    if not EMBEDDINGS_FILE.exists():
        raise FileNotFoundError(
            f"{EMBEDDINGS_FILE} missing — run "
            "`uv run scripts/regenerate_fixture_embeddings.py` with TEI up."
        )
    arr = np.load(EMBEDDINGS_FILE)
    if arr.shape != (len(CHUNKS), 1024):
        raise ValueError(
            f"embeddings.npy shape {arr.shape} does not match "
            f"({len(CHUNKS)}, 1024) implied by corpus.py"
        )
    return arr


def _halfvec(values: np.ndarray) -> str:
    return "[" + ",".join(f"{float(v):.6f}" for v in values) + "]"


async def seed(conn: AsyncConnection) -> None:
    embeddings = _load_embeddings()

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

    doc_rows = []
    for d in DOCUMENTS:
        abstract_sql = (
            "NULL" if d.abstract is None
            else "'" + d.abstract.replace("'", "''") + "'"
        )
        doc_rows.append(
            f"({d.id}, '{d.visibility}', '{d.publication_status}', "
            f"'{d.titulo.replace(chr(39), chr(39) * 2)}', '{d.fecha.isoformat()}', "
            f"'{d.area_path}', '{d.tipo}', {abstract_sql}, "
            f"{'now()' if d.soft_deleted else 'NULL'}, "
            f"{'now()' if d.moderation_hidden else 'NULL'})"
        )
    await conn.execute(
        text(
            "INSERT INTO documents (id, visibility, publication_status, titulo, "
            "fecha, area_path, tipo, abstract, soft_deleted_at, moderation_hidden_at) "
            "VALUES " + ",".join(doc_rows) + " ON CONFLICT (id) DO NOTHING"
        )
    )

    for i, c in enumerate(CHUNKS):
        await conn.execute(
            text(
                "INSERT INTO chunks (id, doc_id, chunk_seq, is_headline, "
                "body_text, embedding, embedding_model_version) "
                "VALUES (:id, :doc_id, :seq, :hl, :body, "
                f"'{_halfvec(embeddings[i])}'::halfvec(1024), :mv) "
                "ON CONFLICT (id) DO NOTHING"
            ),
            {
                "id": c.id,
                "doc_id": c.doc_id,
                "seq": c.chunk_seq,
                "hl": c.is_headline,
                "body": c.body_text,
                "mv": EMBEDDING_MODEL_VERSION,
            },
        )

    await conn.execute(
        text(
            "SELECT setval('chunks_id_seq', (SELECT max(id) FROM chunks))"
        )
    )
