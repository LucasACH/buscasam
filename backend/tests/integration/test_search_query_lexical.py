import pytest
from sqlalchemy import text

from buscasam.core import auth, search_query
from buscasam.core.auth import UserCtx
from tests.factories import make_chunk, make_document, make_user


async def test_search_lexical_invitado_only(session):
    """Mixed-visibility corpus: only publico+published+visible doc is returned."""
    publico_id = await make_document(
        session,
        titulo="Búsqueda léxica de prueba",
        abstract="Documento público sobre búsqueda léxica.",
    )
    await make_chunk(
        session,
        publico_id,
        is_headline=True,
        body_text="Búsqueda léxica de prueba. Documento público sobre búsqueda léxica.",
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
            titulo="Búsqueda léxica oculta",
            abstract="Documento que NO debería aparecer en búsqueda léxica.",
            **kwargs,
        )
        await make_chunk(
            session,
            hidden_id,
            is_headline=True,
            body_text="Búsqueda léxica oculta. NO debería aparecer en búsqueda léxica.",
        )

    await session.commit()

    result = await search_query.run(
        session,
        filters=search_query.Filters(q="búsqueda léxica"),
        user_ctx=auth.GUEST,
    )

    assert [row.doc_id for row in result.rows] == [publico_id]
    assert result.total == 1


async def test_search_lexical_snippet_has_mark_highlights(session):
    """ts_headline injects <mark> around matched terms in the snippet."""
    doc_id = await make_document(
        session,
        titulo="Documento sobre redes neuronales",
        abstract="Estudio detallado de las redes neuronales profundas en español.",
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
        filters=search_query.Filters(q="redes neuronales"),
        user_ctx=auth.GUEST,
    )

    assert len(result.rows) == 1
    snippet = result.rows[0].snippet
    assert "<mark>redes</mark>" in snippet
    assert "<mark>neuronales</mark>" in snippet


@pytest.mark.parametrize("role", [None, "estudiante", "docente"])
async def test_search_lexical_excludes_indexed_candidate_replacement(session, role):
    doc_id = await make_document(
        session,
        titulo="Contenido vigente",
        abstract="Resumen aprobado.",
    )
    await make_chunk(
        session,
        doc_id,
        chunk_seq=0,
        is_headline=True,
        body_text="Contenido vigente aprobado.",
    )
    candidate_id = (
        await session.execute(
            text(
                "INSERT INTO document_versions "
                "(doc_id, version_no, sha256, original_filename, bytes, mime, "
                " index_status, is_current) "
                "VALUES (:doc, 2, decode(repeat('02', 32), 'hex'), 'replacement.pdf', "
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
            "VALUES (:doc, 1, false, 'filtracioncandidata secreta', 'm', :version, false)"
        ),
        {"doc": doc_id, "version": candidate_id},
    )
    user_ctx = auth.GUEST
    if role is not None:
        user_id = await make_user(session, role=role)
        user_ctx = UserCtx(user_id=user_id, is_unsam=True, role=role)

    result = await search_query.run(
        session,
        filters=search_query.Filters(q="filtracioncandidata"),
        user_ctx=user_ctx,
    )

    assert result.rows == []


async def test_search_lexical_total_saturates_at_relevance_cap(session):
    """When the matching set exceeds the top-200 cap, total saturates at 200."""
    for i in range(205):
        doc_id = await make_document(
            session,
            titulo=f"Estudio único {i} sobre quimica molecular",
            abstract="Investigación sobre quimica molecular avanzada.",
        )
        await make_chunk(
            session,
            doc_id,
            is_headline=True,
            body_text=f"Estudio único {i} sobre quimica molecular avanzada.",
        )
    await session.commit()

    result = await search_query.run(
        session,
        filters=search_query.Filters(q="quimica molecular"),
        user_ctx=auth.GUEST,
    )

    assert result.total == 200
    assert len(result.rows) == 10
