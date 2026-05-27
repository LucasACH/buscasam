from datetime import date

from sqlalchemy import text

from buscasam.core import auth, search_query
from tests.factories import make_chunk, make_document


async def test_recientes_orders_by_fecha_desc_with_q_filter(session):
    """orden=recientes returns matching docs sorted by fecha desc; total exact."""
    old_id = await make_document(
        session,
        titulo="Estudio antiguo sobre redes",
        abstract="Investigación temprana sobre redes neuronales.",
        fecha=date(2018, 6, 1),
    )
    await make_chunk(
        session,
        old_id,
        is_headline=True,
        body_text="Estudio antiguo sobre redes neuronales en 2018.",
    )

    mid_id = await make_document(
        session,
        titulo="Estudio intermedio sobre redes",
        abstract="Investigación sobre redes neuronales.",
        fecha=date(2022, 6, 1),
    )
    await make_chunk(
        session,
        mid_id,
        is_headline=True,
        body_text="Estudio intermedio sobre redes neuronales en 2022.",
    )

    new_id = await make_document(
        session,
        titulo="Estudio reciente sobre redes",
        abstract="Investigación reciente sobre redes neuronales.",
        fecha=date(2024, 6, 1),
    )
    await make_chunk(
        session,
        new_id,
        is_headline=True,
        body_text="Estudio reciente sobre redes neuronales en 2024.",
    )
    await session.commit()

    result = await search_query.run(
        session,
        filters=search_query.Filters(q="redes neuronales", orden="recientes"),
        user_ctx=auth.GUEST,
    )

    assert [row.doc_id for row in result.rows] == [new_id, mid_id, old_id]
    assert result.total == 3
    assert result.saturated is False


async def test_recientes_snippet_has_mark_highlights_when_q_set(session):
    """orden=recientes + q: ts_headline injects <mark> around matched terms (PRD US-6)."""
    doc_id = await make_document(
        session,
        titulo="Documento sobre redes neuronales",
        abstract="Estudio detallado de las redes neuronales profundas en español.",
        fecha=date(2024, 6, 1),
    )
    await make_chunk(
        session,
        doc_id,
        is_headline=True,
        body_text=(
            "Documento sobre redes neuronales. Estudio detallado de las redes "
            "neuronales profundas en español."
        ),
    )
    await session.commit()

    result = await search_query.run(
        session,
        filters=search_query.Filters(q="redes neuronales", orden="recientes"),
        user_ctx=auth.GUEST,
    )

    assert len(result.rows) == 1
    snippet = result.rows[0].snippet
    assert "<mark>redes</mark>" in snippet
    assert "<mark>neuronales</mark>" in snippet


async def test_recientes_with_query_excludes_indexed_candidate_replacement(session):
    doc_id = await make_document(
        session,
        titulo="Documento vigente",
        abstract="Resumen publicado.",
        fecha=date(2024, 6, 1),
    )
    await make_chunk(
        session,
        doc_id,
        chunk_seq=0,
        is_headline=True,
        body_text="Texto vigente aprobado.",
    )
    candidate_id = (
        await session.execute(
            text(
                "INSERT INTO document_versions "
                "(doc_id, version_no, sha256, original_filename, bytes, mime, "
                " index_status, is_current) "
                "VALUES (:doc, 2, decode(repeat('04', 32), 'hex'), 'replacement.pdf', "
                " 10, 'application/pdf', 'indexed', false) RETURNING id"
            ),
            {"doc": doc_id},
        )
    ).scalar_one()
    await session.execute(
        text(
            "INSERT INTO chunks "
            "(doc_id, chunk_seq, is_headline, body_text, embedding_model_version, "
            " version_id, is_current) "
            "VALUES (:doc, 1, false, 'recientecandidata reservada', 'm', :version, false)"
        ),
        {"doc": doc_id, "version": candidate_id},
    )

    result = await search_query.run(
        session,
        filters=search_query.Filters(q="recientecandidata", orden="recientes"),
        user_ctx=auth.GUEST,
    )

    assert result.rows == []


async def test_recientes_snippet_is_abstract_prefix_when_q_empty(session):
    """orden=recientes browse mode: snippet is abstract prefix (no chunks join)."""
    doc_id = await make_document(
        session,
        titulo="Doc",
        abstract="A" * 250,
        fecha=date(2024, 6, 1),
    )
    await make_chunk(session, doc_id, is_headline=True, body_text="Doc cuerpo.")
    await session.commit()

    result = await search_query.run(
        session,
        filters=search_query.Filters(q="", orden="recientes"),
        user_ctx=auth.GUEST,
    )

    assert len(result.rows) == 1
    assert result.rows[0].snippet == "A" * 200


async def test_recientes_enforces_invitado_visibility(session):
    """orden=recientes respects the invitado predicate (hidden docs excluded)."""
    publico_id = await make_document(
        session,
        titulo="Documento público",
        abstract="Documento público para recientes.",
        fecha=date(2024, 1, 1),
    )
    await make_chunk(
        session,
        publico_id,
        is_headline=True,
        body_text="Documento público sobre tema cualquiera.",
    )

    for kwargs in (
        {"visibility": "interno"},
        {"visibility": "privado"},
        {"publication_status": "draft"},
        {"soft_deleted": True},
        {"moderation_hidden": True},
    ):
        hidden_id = await make_document(
            session,
            titulo="Documento oculto",
            abstract="No debería aparecer en recientes.",
            fecha=date(2025, 1, 1),
            **kwargs,
        )
        await make_chunk(
            session,
            hidden_id,
            is_headline=True,
            body_text="Documento oculto que no debería aparecer.",
        )
    await session.commit()

    result = await search_query.run(
        session,
        filters=search_query.Filters(q="", orden="recientes"),
        user_ctx=auth.GUEST,
    )

    assert [row.doc_id for row in result.rows] == [publico_id]
    assert result.total == 1


async def test_recientes_uncapped_pagination(session):
    """orden=recientes accepts pagina>20 without saturating; in-range pages return rows."""
    ids: list[int] = []
    for i in range(25):
        doc_id = await make_document(
            session,
            titulo=f"Documento {i}",
            abstract=f"Abstract {i}",
            fecha=date(2024, 1, 1),
        )
        await make_chunk(
            session,
            doc_id,
            is_headline=True,
            body_text=f"Documento {i} cuerpo.",
        )
        ids.append(doc_id)
    await session.commit()

    page21 = await search_query.run(
        session,
        filters=search_query.Filters(q="", orden="recientes", pagina=21),
        user_ctx=auth.GUEST,
    )
    assert page21.saturated is False
    assert page21.rows == []

    page3 = await search_query.run(
        session,
        filters=search_query.Filters(q="", orden="recientes", pagina=3),
        user_ctx=auth.GUEST,
    )
    assert page3.total == 25
    assert page3.saturated is False
    assert len(page3.rows) == 5
