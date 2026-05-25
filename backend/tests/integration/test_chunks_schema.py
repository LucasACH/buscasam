from sqlalchemy import text


async def test_chunk_body_tsv_uses_es_unaccent_and_halfvec_accepts_1024(session):
    await session.execute(
        text(
            "INSERT INTO documents (id, visibility, publication_status, "
            "titulo, fecha, area_path, tipo) VALUES "
            "(30, 'publico', 'published', 'd30', '2024-01-01', "
            "'escuela_ciencia', 'paper')"
        )
    )
    emb_literal = "[" + ",".join(["0.1"] * 1024) + "]"
    await session.execute(
        text(
            "INSERT INTO chunks (id, doc_id, chunk_seq, is_headline, body_text, "
            "embedding, embedding_model_version) VALUES "
            f"(100, 30, 0, true, 'Análisis estadístico de redes neuronales', "
            f"'{emb_literal}'::halfvec(1024), 'e5-large@abc123')"
        )
    )
    await session.commit()

    rows = (
        await session.execute(
            text(
                "SELECT id FROM chunks "
                "WHERE body_tsv @@ to_tsquery('es_unaccent', 'analisis')"
            )
        )
    ).scalars().all()
    assert rows == [100]
