"""search_query.run threads UserCtx through readable_where and exposes
`visibility` per row (PRD-2 reach into interno/privado)."""
from buscasam.core import search_query
from buscasam.core.auth import GUEST, UserCtx
from buscasam.core.search_query import Filters
from tests.factories import make_chunk, make_document, make_user


async def test_run_threads_user_ctx_and_exposes_visibility(session):
    publico = await make_document(
        session,
        visibility="publico",
        titulo="Redes públicas",
        abstract="Estudio sobre redes neuronales.",
    )
    await make_chunk(
        session, publico, is_headline=True, body_text="Redes neuronales públicas."
    )
    interno = await make_document(
        session,
        visibility="interno",
        titulo="Redes internas",
        abstract="Notas internas sobre redes neuronales.",
    )
    await make_chunk(
        session, interno, is_headline=True, body_text="Redes neuronales internas."
    )
    await session.commit()

    filters = Filters(q="redes neuronales")

    guest = await search_query.run(session, filters=filters, user_ctx=GUEST)
    assert {r.doc_id for r in guest.rows} == {publico}
    assert {r.visibility for r in guest.rows} == {"publico"}

    uid = await make_user(session, role="estudiante")
    unsam = UserCtx(user_id=uid, is_unsam=True, role="estudiante")
    authed = await search_query.run(session, filters=filters, user_ctx=unsam)
    assert {r.doc_id for r in authed.rows} == {publico, interno}
    assert {r.doc_id: r.visibility for r in authed.rows} == {
        publico: "publico",
        interno: "interno",
    }
