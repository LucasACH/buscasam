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
            "INSERT INTO document_versions "
            "(doc_id, version_no, sha256, original_filename, bytes, mime, "
            " is_current, index_status) VALUES "
            "(30, 1, decode(repeat('00', 32), 'hex'), 'd30.pdf', 1, "
            " 'application/pdf', true, 'indexed')"
        )
    )
    await session.execute(
        text(
            "INSERT INTO chunks (id, doc_id, chunk_seq, is_headline, body_text, "
            "embedding, embedding_model_version, version_id, is_current) VALUES "
            f"(100, 30, 0, true, 'Análisis estadístico de redes neuronales', "
            f"'{emb_literal}'::halfvec(1024), 'e5-large@abc123', "
            "(SELECT id FROM document_versions WHERE doc_id = 30), true)"
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
