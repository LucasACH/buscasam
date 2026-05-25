"""Hybrid retrieval — semantic CTE + RRF fusion + match floor (slice 5)."""
from __future__ import annotations

import numpy as np

from buscasam.core import search_query
from tests.factories import make_chunk, make_document


def _unit(dim: int) -> np.ndarray:
    v = np.zeros(1024, dtype=np.float16)
    v[dim] = 1.0
    return v


async def test_search_hybrid_returns_pure_semantic_hit(session):
    """Query embedding aligned to doc A surfaces A even with zero lexical overlap."""
    a_id = await make_document(
        session,
        titulo="Documento sobre física cuántica",
        abstract="Estudio sobre partículas subatómicas y su comportamiento.",
    )
    await make_chunk(
        session, a_id, is_headline=True,
        body_text="Documento sobre física cuántica.",
        embedding=_unit(0),
    )

    b_id = await make_document(
        session,
        titulo="Documento sobre literatura",
        abstract="Estudio sobre novelas argentinas del siglo XX.",
    )
    await make_chunk(
        session, b_id, is_headline=True,
        body_text="Documento sobre literatura.",
        embedding=_unit(1),
    )
    await session.commit()

    result = await search_query.run(
        session,
        filters=search_query.Filters(q="zorgblat"),
        user_ctx=search_query.UserCtx(role="invitado"),
        embedding=_unit(0),
    )

    assert [r.doc_id for r in result.rows] == [a_id]
    assert result.rows[0].snippet == (
        "Estudio sobre partículas subatómicas y su comportamiento."
    )


async def test_search_excludes_below_floor(session):
    """Pure-semantic row with cosine below MIN_SEMANTIC_SIMILARITY is excluded."""
    doc_id = await make_document(
        session,
        titulo="Documento irrelevante",
        abstract="Contenido sin relación con la consulta.",
    )
    half_sim = np.zeros(1024, dtype=np.float16)
    half_sim[0] = np.float16(0.5)
    half_sim[1] = np.float16(np.sqrt(0.75))
    await make_chunk(
        session, doc_id, is_headline=True,
        body_text="Documento irrelevante para la consulta.",
        embedding=half_sim,
    )
    await session.commit()

    q_vec = np.zeros(1024, dtype=np.float16)
    q_vec[0] = 1.0

    result = await search_query.run(
        session,
        filters=search_query.Filters(q="zorgblat"),
        user_ctx=search_query.UserCtx(role="invitado"),
        embedding=q_vec,
    )

    assert result.rows == []
    assert result.total == 0


async def test_search_snippet_rule_splits_by_row_source(session):
    """Lexical-matching row gets <mark> snippet; pure-semantic row gets abstract[:200]."""
    lex_id = await make_document(
        session,
        titulo="Doc léxico",
        abstract="Resumen del documento léxico.",
    )
    await make_chunk(
        session, lex_id, is_headline=True,
        body_text="Contiene alphabravo en el texto.",
        embedding=_unit(2),
    )

    sem_id = await make_document(
        session,
        titulo="Doc semántico",
        abstract="Resumen del documento semántico relacionado.",
    )
    await make_chunk(
        session, sem_id, is_headline=True,
        body_text="Sin coincidencia textual con la consulta.",
        embedding=_unit(0),
    )
    await session.commit()

    result = await search_query.run(
        session,
        filters=search_query.Filters(q="alphabravo"),
        user_ctx=search_query.UserCtx(role="invitado"),
        embedding=_unit(0),
    )

    rows_by_id = {r.doc_id: r for r in result.rows}
    assert lex_id in rows_by_id
    assert sem_id in rows_by_id
    assert "<mark>alphabravo</mark>" in rows_by_id[lex_id].snippet
    assert rows_by_id[sem_id].snippet == "Resumen del documento semántico relacionado."
