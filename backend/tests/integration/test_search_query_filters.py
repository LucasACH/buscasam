from datetime import date

from buscasam.core import auth, search_query
from tests.factories import make_chunk, make_document


async def test_tipo_filter_narrows_to_selected_tipos(session):
    """tipos restricts results to documents whose tipo is in the set."""
    tesis_id = await make_document(
        session,
        titulo="Tesis sobre redes neuronales",
        abstract="Investigación sobre redes neuronales profundas.",
        tipo="tesis",
    )
    await make_chunk(
        session,
        tesis_id,
        is_headline=True,
        body_text="Tesis sobre redes neuronales profundas.",
    )

    paper_id = await make_document(
        session,
        titulo="Paper sobre redes neuronales",
        abstract="Artículo breve sobre redes neuronales.",
        tipo="paper",
    )
    await make_chunk(
        session,
        paper_id,
        is_headline=True,
        body_text="Paper sobre redes neuronales convolucionales.",
    )

    monografia_id = await make_document(
        session,
        titulo="Monografía sobre redes neuronales",
        abstract="Resumen sobre redes neuronales.",
        tipo="monografia",
    )
    await make_chunk(
        session,
        monografia_id,
        is_headline=True,
        body_text="Monografía sobre redes neuronales recurrentes.",
    )
    await session.commit()

    single = await search_query.run(
        session,
        filters=search_query.Filters(q="redes neuronales", tipos=("tesis",)),
        user_ctx=auth.GUEST,
    )
    assert {row.doc_id for row in single.rows} == {tesis_id}

    multi = await search_query.run(
        session,
        filters=search_query.Filters(q="redes neuronales", tipos=("tesis", "paper")),
        user_ctx=auth.GUEST,
    )
    assert {row.doc_id for row in multi.rows} == {tesis_id, paper_id}


async def test_fecha_year_range_narrows(session):
    """desde/hasta restricts results to documents whose fecha year is in [desde, hasta]."""
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
        titulo="Estudio reciente sobre redes",
        abstract="Investigación reciente sobre redes neuronales.",
        fecha=date(2022, 6, 1),
    )
    await make_chunk(
        session,
        mid_id,
        is_headline=True,
        body_text="Estudio reciente sobre redes neuronales en 2022.",
    )

    new_id = await make_document(
        session,
        titulo="Estudio actual sobre redes",
        abstract="Investigación actual sobre redes neuronales.",
        fecha=date(2025, 6, 1),
    )
    await make_chunk(
        session,
        new_id,
        is_headline=True,
        body_text="Estudio actual sobre redes neuronales en 2025.",
    )
    await session.commit()

    inside = await search_query.run(
        session,
        filters=search_query.Filters(q="redes neuronales", desde=2020, hasta=2023),
        user_ctx=auth.GUEST,
    )
    assert {row.doc_id for row in inside.rows} == {mid_id}

    open_ended = await search_query.run(
        session,
        filters=search_query.Filters(q="redes neuronales", desde=2022),
        user_ctx=auth.GUEST,
    )
    assert {row.doc_id for row in open_ended.rows} == {mid_id, new_id}

    out_of_range = await search_query.run(
        session,
        filters=search_query.Filters(q="redes neuronales", desde=2030, hasta=2040),
        user_ctx=auth.GUEST,
    )
    assert out_of_range.rows == []
    assert out_of_range.total == 0
