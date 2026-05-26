from buscasam.core import auth, search_query
from tests.factories import make_chunk, make_document


async def test_area_filter_narrows_to_subtree(session):
    """area_path filter restricts results to that ltree subtree."""
    ciencia_id = await make_document(
        session,
        titulo="Búsqueda híbrida en repositorios",
        abstract="Estudio sobre fusión léxico-semántica.",
        area_path="escuela_ciencia.carrera_informatica",
    )
    await make_chunk(
        session,
        ciencia_id,
        is_headline=True,
        body_text="Búsqueda híbrida en repositorios académicos.",
    )

    humanidades_id = await make_document(
        session,
        titulo="Búsqueda híbrida de fuentes literarias",
        abstract="Métodos mixtos de búsqueda híbrida en archivos.",
        area_path="escuela_humanidades.carrera_letras",
    )
    await make_chunk(
        session,
        humanidades_id,
        is_headline=True,
        body_text="Búsqueda híbrida de fuentes literarias y archivos.",
    )
    await session.commit()

    result = await search_query.run(
        session,
        filters=search_query.Filters(q="búsqueda híbrida", area_path="escuela_ciencia"),
        user_ctx=auth.GUEST,
    )

    assert [row.doc_id for row in result.rows] == [ciencia_id]
    assert result.total == 1


async def test_empty_area_applies_no_filter(session):
    """area_path=None returns matches from any subtree."""
    ciencia_id = await make_document(
        session,
        titulo="Búsqueda híbrida en repositorios",
        abstract="Estudio sobre fusión léxico-semántica.",
        area_path="escuela_ciencia.carrera_informatica",
    )
    await make_chunk(
        session,
        ciencia_id,
        is_headline=True,
        body_text="Búsqueda híbrida en repositorios académicos.",
    )

    humanidades_id = await make_document(
        session,
        titulo="Búsqueda híbrida de fuentes literarias",
        abstract="Métodos mixtos de búsqueda híbrida en archivos.",
        area_path="escuela_humanidades.carrera_letras",
    )
    await make_chunk(
        session,
        humanidades_id,
        is_headline=True,
        body_text="Búsqueda híbrida de fuentes literarias y archivos.",
    )
    await session.commit()

    result = await search_query.run(
        session,
        filters=search_query.Filters(q="búsqueda híbrida"),
        user_ctx=auth.GUEST,
    )

    assert {row.doc_id for row in result.rows} == {ciencia_id, humanidades_id}
    assert result.total == 2
