import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from buscasam.api.app import app
from buscasam.api.deps import get_session
from tests.factories import make_chunk, make_document


@pytest_asyncio.fixture
async def client(session):
    async def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def test_search_endpoint_returns_publico_only(client, session):
    publico_id = await make_document(
        session,
        titulo="Búsqueda léxica vía API",
        abstract="Documento público sobre búsqueda léxica vía API.",
    )
    await make_chunk(
        session,
        publico_id,
        is_headline=True,
        body_text="Búsqueda léxica vía API. Documento público.",
    )

    interno_id = await make_document(
        session,
        visibility="interno",
        titulo="Búsqueda léxica interna",
        abstract="Notas internas sobre búsqueda léxica.",
    )
    await make_chunk(
        session,
        interno_id,
        is_headline=True,
        body_text="Búsqueda léxica interna. Notas internas.",
    )
    await session.commit()

    r = await client.get("/api/search", params={"q": "búsqueda léxica", "pagina": 1})

    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert [row["doc_id"] for row in data["results"]] == [publico_id]
    assert data["results"][0]["titulo"] == "Búsqueda léxica vía API"


async def test_search_endpoint_rejects_pagina_over_20(client):
    r = await client.get("/api/search", params={"q": "anything", "pagina": 21})
    assert r.status_code == 422
