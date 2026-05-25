import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from buscasam.api.app import create_app
from buscasam.api.deps import get_session
from tests.factories import make_chunk, make_document


@pytest_asyncio.fixture
async def client(session):
    async def _override():
        yield session

    app = create_app()
    app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


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


async def test_search_endpoint_area_param_narrows(client, session):
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

    unfiltered = await client.get("/api/search", params={"q": "búsqueda híbrida"})
    assert unfiltered.status_code == 200
    assert {row["doc_id"] for row in unfiltered.json()["results"]} == {
        ciencia_id,
        humanidades_id,
    }

    narrowed = await client.get(
        "/api/search", params={"q": "búsqueda híbrida", "area": "escuela_ciencia"}
    )
    assert narrowed.status_code == 200
    data = narrowed.json()
    assert [row["doc_id"] for row in data["results"]] == [ciencia_id]
    assert data["total"] == 1


async def test_search_endpoint_rejects_malformed_area(client):
    for bad in ("foo!bar", "a.b.", ".a.b", "Escuelas", "a..b"):
        r = await client.get("/api/search", params={"q": "anything", "area": bad})
        assert r.status_code == 422, f"expected 422 for area={bad!r}, got {r.status_code}"
