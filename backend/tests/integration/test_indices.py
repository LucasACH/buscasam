from sqlalchemy import text

from buscasam.core.document_access import invitado_fragment


async def test_hnsw_index_chosen_for_cosine_topk(session):
    await session.execute(
        text(
            "INSERT INTO documents (id, visibility, publication_status, "
            "titulo, fecha, area_path, tipo) VALUES "
            "(40, 'publico', 'published', 'd40', '2024-01-01', "
            "'escuela_ciencia', 'paper')"
        )
    )
    for i in range(8):
        emb = "[" + ",".join([f"{(0.01 * (i + 1)):.6f}"] * 1024) + "]"
        await session.execute(
            text(
                "INSERT INTO chunks (doc_id, chunk_seq, is_headline, body_text, "
                "embedding, embedding_model_version) VALUES "
                f"(40, {i}, false, 'body {i}', '{emb}'::halfvec(1024), 'e5')"
            )
        )
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
    await session.execute(
        text(
            "INSERT INTO documents (id, visibility, publication_status, "
            "titulo, fecha, area_path, tipo) VALUES "
            "(50, 'publico', 'published', 'd50', '2024-01-01', "
            "'escuela_ciencia', 'paper')"
        )
    )
    emb = "[" + ",".join(["0.1"] * 1024) + "]"
    for i in range(8):
        await session.execute(
            text(
                "INSERT INTO chunks (doc_id, chunk_seq, is_headline, body_text, "
                "embedding, embedding_model_version) VALUES "
                f"(50, {i}, false, 'redes neuronales ejemplo {i}', "
                f"'{emb}'::halfvec(1024), 'e5')"
            )
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
    inserts = []
    for i in range(20):
        inserts.append(
            f"({200 + i}, 'publico', 'published', "
            f"'d{200 + i}', '2024-01-{(i % 28) + 1:02d}', "
            f"'escuela_ciencia', 'paper')"
        )
    await session.execute(
        text(
            "INSERT INTO documents (id, visibility, publication_status, "
            "titulo, fecha, area_path, tipo) VALUES " + ",".join(inserts)
        )
    )
    await session.commit()

    await session.execute(text("SET LOCAL enable_seqscan = off"))
    sql, _ = invitado_fragment()
    plan_lines = (
        await session.execute(
            text(
                f"EXPLAIN SELECT id FROM documents WHERE {sql} "
                "ORDER BY fecha DESC LIMIT 10"
            )
        )
    ).scalars().all()
    plan = "\n".join(plan_lines)

    assert "documents_publico_recientes" in plan, plan
