from buscasam.core import auth, search_query
from tests.factories import make_chunk, make_document


async def test_lexical_misses_typo_but_fuzzy_matches(session):
    """`descrago` finds nothing lexically yet trigram-matches `descargo`."""
    doc_id = await make_document(
        session,
        titulo="Multa",
        abstract="Descargo ante un acta de comprobación por exceso de velocidad.",
    )
    await make_chunk(
        session,
        doc_id,
        is_headline=True,
        body_text="Francisco presenta un descargo ante un acta de comprobación.",
    )
    await session.commit()

    lexical = await search_query.run(
        session,
        filters=search_query.Filters(q="descrago"),
        user_ctx=auth.GUEST,
    )
    assert lexical.total == 0

    fuzzy = await search_query.run_fuzzy(
        session,
        filters=search_query.Filters(q="descrago"),
        user_ctx=auth.GUEST,
    )
    assert [row.doc_id for row in fuzzy.rows] == [doc_id]
    assert fuzzy.total == 1


async def test_fuzzy_respects_invitado_visibility(session):
    """Non-público / unpublished docs never leak through the fuzzy path."""
    for kwargs in (
        {"visibility": "interno"},
        {"visibility": "privado"},
        {"publication_status": "draft"},
        {"soft_deleted": True},
        {"moderation_hidden": True},
    ):
        hidden_id = await make_document(session, titulo="Oculto", **kwargs)
        await make_chunk(
            session,
            hidden_id,
            is_headline=True,
            body_text="Francisco presenta un descargo ante un acta.",
        )
    await session.commit()

    fuzzy = await search_query.run_fuzzy(
        session,
        filters=search_query.Filters(q="descrago"),
        user_ctx=auth.GUEST,
    )
    assert fuzzy.rows == []
