from datetime import date

import numpy as np
from sqlalchemy import text

from buscasam.core.document_access import invitado_where
from tests.factories import make_chunk, make_document


async def test_hnsw_index_chosen_for_cosine_topk(session):
    doc_id = await make_document(session)
    for i in range(8):
        vec = np.full(1024, 0.01 * (i + 1), dtype=np.float16)
        await make_chunk(session, doc_id, chunk_seq=i, embedding=vec)
    await session.commit()

    await session.execute(text("SET LOCAL enable_seqscan = off"))
    q = "[" + ",".join(["0.5"] * 1024) + "]"
    plan_lines = (
        await session.execute(
            text(
                "EXPLAIN SELECT id FROM chunks "
                f"ORDER BY embedding <=> '{q}'::halfvec(1024) LIMIT 10"
            )
        )
    ).scalars().all()
    plan = "\n".join(plan_lines)

    assert "chunks_embedding_hnsw" in plan, plan


async def test_gin_index_chosen_for_body_tsv_match(session):
    doc_id = await make_document(session)
    for i in range(8):
        await make_chunk(
            session, doc_id, chunk_seq=i, body_text=f"redes neuronales ejemplo {i}"
        )
    await session.commit()

    await session.execute(text("SET LOCAL enable_seqscan = off"))
    plan_lines = (
        await session.execute(
            text(
                "EXPLAIN SELECT id FROM chunks "
                "WHERE body_tsv @@ to_tsquery('es_unaccent', 'neuronales')"
            )
        )
    ).scalars().all()
    plan = "\n".join(plan_lines)

    assert "chunks_body_tsv_gin" in plan, plan


async def test_partial_btree_chosen_for_invitado_recientes(session):
    for i in range(20):
        await make_document(session, fecha=date(2024, 1, (i % 28) + 1))
    await session.commit()

    await session.execute(text("SET LOCAL enable_seqscan = off"))
    where = invitado_where("d")
    plan_lines = (
        await session.execute(
            text(
                f"EXPLAIN SELECT d.id FROM documents d WHERE {where} "
                "ORDER BY d.fecha DESC LIMIT 10"
            )
        )
    ).scalars().all()
    plan = "\n".join(plan_lines)

    assert "documents_publico_recientes" in plan, plan
