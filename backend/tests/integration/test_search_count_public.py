"""count_public_documents: the público catalog size for the landing footnote
(issue #109, module map §core/search)."""
from __future__ import annotations

from buscasam.core import search
from tests.factories import make_document


async def test_counts_only_publico_published_visible_documents(session):
    await make_document(session, visibility="publico")
    await make_document(session, visibility="publico")
    await make_document(session, visibility="interno")
    await make_document(session, visibility="privado")
    await make_document(session, visibility="publico", publication_status="draft")
    await make_document(session, visibility="publico", soft_deleted=True)
    await make_document(session, visibility="publico", moderation_hidden=True)
    await session.commit()

    assert await search.count_public_documents(session) == 2


async def test_empty_catalog_counts_zero(session):
    await session.commit()
    assert await search.count_public_documents(session) == 0
