from datetime import date

from buscasam.core import search_query
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
        user_ctx=search_query.UserCtx(role="invitado"),
    )

    assert [row.doc_id for row in result.rows] == [new_id, mid_id, old_id]
    assert result.total == 3
    assert result.saturated is False


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
        user_ctx=search_query.UserCtx(role="invitado"),
    )

    assert [row.doc_id for row in result.rows] == [publico_id]
    assert result.total == 1


async def test_recientes_uncapped_pagination(session):
    """orden=recientes accepts pagina>20; total stays exact (no 200+ saturation)."""
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
        user_ctx=search_query.UserCtx(role="invitado"),
    )

    assert page21.total == 25
    assert page21.saturated is False
    assert page21.rows == []
