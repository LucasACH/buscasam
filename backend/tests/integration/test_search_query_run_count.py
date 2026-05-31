"""run_count returns the same total the full run() would, without paging/headline."""

from __future__ import annotations

import numpy as np

from buscasam.core import auth, search_query
from tests.factories import make_chunk, make_document


def _unit(dim: int) -> np.ndarray:
    v = np.zeros(1024, dtype=np.float16)
    v[dim] = 1.0
    return v


async def _seed(session) -> None:
    physics_id = await make_document(
        session,
        titulo="Documento sobre física cuántica",
        abstract="Estudio sobre partículas subatómicas.",
        area_path="escuela_ciencia",
        tipo="tesis",
    )
    await make_chunk(
        session,
        physics_id,
        is_headline=True,
        body_text="Documento sobre redes neuronales y física cuántica.",
        embedding=_unit(0),
    )

    lit_id = await make_document(
        session,
        titulo="Documento sobre literatura",
        abstract="Estudio sobre novelas argentinas.",
        area_path="escuela_humanidades",
        tipo="paper",
    )
    await make_chunk(
        session,
        lit_id,
        is_headline=True,
        body_text="Documento sobre redes neuronales en la literatura.",
        embedding=_unit(1),
    )
    await session.commit()


async def test_run_count_matches_lexical_total(session):
    await _seed(session)
    filters = search_query.Filters(q="redes neuronales")
    full = await search_query.run(session, filters=filters, user_ctx=auth.GUEST)
    count = await search_query.run_count(session, filters=filters, user_ctx=auth.GUEST)
    assert count == full.total == 2


async def test_run_count_matches_lexical_total_with_filter(session):
    await _seed(session)
    filters = search_query.Filters(q="redes neuronales", tipos=("tesis",))
    full = await search_query.run(session, filters=filters, user_ctx=auth.GUEST)
    count = await search_query.run_count(session, filters=filters, user_ctx=auth.GUEST)
    assert count == full.total == 1


async def test_run_count_matches_hybrid_total(session):
    await _seed(session)
    filters = search_query.Filters(q="redes neuronales")
    full = await search_query.run(
        session, filters=filters, user_ctx=auth.GUEST, embedding=_unit(0)
    )
    count = await search_query.run_count(
        session, filters=filters, user_ctx=auth.GUEST, embedding=_unit(0)
    )
    assert count == full.total == 2


async def test_run_count_matches_hybrid_total_with_filter(session):
    await _seed(session)
    filters = search_query.Filters(q="redes neuronales", area_path="escuela_ciencia")
    full = await search_query.run(
        session, filters=filters, user_ctx=auth.GUEST, embedding=_unit(0)
    )
    count = await search_query.run_count(
        session, filters=filters, user_ctx=auth.GUEST, embedding=_unit(0)
    )
    assert count == full.total == 1


async def test_run_count_matches_recientes_with_q(session):
    await _seed(session)
    filters = search_query.Filters(q="redes neuronales", orden="recientes")
    full = await search_query.run(session, filters=filters, user_ctx=auth.GUEST)
    count = await search_query.run_count(session, filters=filters, user_ctx=auth.GUEST)
    assert count == full.total == 2


async def test_run_count_matches_recientes_without_q(session):
    await _seed(session)
    filters = search_query.Filters(q="", orden="recientes")
    full = await search_query.run(session, filters=filters, user_ctx=auth.GUEST)
    count = await search_query.run_count(session, filters=filters, user_ctx=auth.GUEST)
    assert count == full.total == 2


async def test_run_count_matches_recientes_without_q_with_filter(session):
    await _seed(session)
    filters = search_query.Filters(
        q="", orden="recientes", area_path="escuela_humanidades"
    )
    full = await search_query.run(session, filters=filters, user_ctx=auth.GUEST)
    count = await search_query.run_count(session, filters=filters, user_ctx=auth.GUEST)
    assert count == full.total == 1
