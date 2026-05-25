from datetime import date

import pytest
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


@pytest.mark.parametrize("bad", ["foo!bar", "a.b.", ".a.b", "Escuelas", "a..b"])
async def test_search_endpoint_rejects_malformed_area(client, bad):
    r = await client.get("/api/search", params={"q": "anything", "area": bad})
    assert r.status_code == 422


async def test_search_endpoint_repeats_tipo_param_for_multi_select(client, session):
    tesis_id = await make_document(
        session,
        titulo="Tesis sobre redes",
        abstract="Tesis detallada sobre redes neuronales.",
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
        titulo="Paper sobre redes",
        abstract="Paper sobre redes neuronales convolucionales.",
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
        titulo="Monografía sobre redes",
        abstract="Monografía sobre redes neuronales recurrentes.",
        tipo="monografia",
    )
    await make_chunk(
        session,
        monografia_id,
        is_headline=True,
        body_text="Monografía sobre redes neuronales recurrentes.",
    )
    await session.commit()

    r = await client.get(
        "/api/search",
        params=[("q", "redes neuronales"), ("tipo", "tesis"), ("tipo", "paper")],
    )
    assert r.status_code == 200
    data = r.json()
    assert {row["doc_id"] for row in data["results"]} == {tesis_id, paper_id}


@pytest.mark.parametrize("bad", ["libro", "TESIS", "", "tesis_invalida"])
async def test_search_endpoint_rejects_unknown_tipo(client, bad):
    r = await client.get(
        "/api/search", params=[("q", "anything"), ("tipo", bad)]
    )
    assert r.status_code == 422


async def test_search_endpoint_desde_hasta_narrow(client, session):
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
    await session.commit()

    r = await client.get(
        "/api/search",
        params={"q": "redes neuronales", "desde": 2020, "hasta": 2023},
    )
    assert r.status_code == 200
    data = r.json()
    assert {row["doc_id"] for row in data["results"]} == {mid_id}


@pytest.mark.parametrize("field", ["desde", "hasta"])
@pytest.mark.parametrize("bad", ["999", "10000", "abc", "20.5", "2024a"])
async def test_search_endpoint_rejects_non_4_digit_year(client, field, bad):
    r = await client.get(
        "/api/search", params={"q": "anything", field: bad}
    )
    assert r.status_code == 422


async def test_search_endpoint_rejects_desde_greater_than_hasta(client):
    r = await client.get(
        "/api/search", params={"q": "anything", "desde": 2025, "hasta": 2020}
    )
    assert r.status_code == 422


async def test_search_endpoint_unfiltered_total_null_when_no_filter(client, session):
    publico_id = await make_document(
        session,
        titulo="Documento público sobre búsqueda léxica",
        abstract="Documento público para probar unfiltered_total.",
        tipo="paper",
    )
    await make_chunk(
        session,
        publico_id,
        is_headline=True,
        body_text="Documento público sobre búsqueda léxica.",
    )
    await session.commit()

    r = await client.get("/api/search", params={"q": "búsqueda léxica"})
    assert r.status_code == 200
    assert r.json()["unfiltered_total"] is None


async def test_search_endpoint_unfiltered_total_respects_visibility(client, session):
    """unfiltered_total counts only invitado-readable docs and is >= total."""
    publico_tesis = await make_document(
        session,
        titulo="Tesis pública sobre redes",
        abstract="Tesis pública sobre redes neuronales.",
        tipo="tesis",
    )
    await make_chunk(
        session,
        publico_tesis,
        is_headline=True,
        body_text="Tesis pública sobre redes neuronales.",
    )

    publico_paper = await make_document(
        session,
        titulo="Paper público sobre redes",
        abstract="Paper público sobre redes neuronales.",
        tipo="paper",
    )
    await make_chunk(
        session,
        publico_paper,
        is_headline=True,
        body_text="Paper público sobre redes neuronales.",
    )

    interno_paper = await make_document(
        session,
        visibility="interno",
        titulo="Paper interno sobre redes",
        abstract="Paper interno sobre redes neuronales.",
        tipo="paper",
    )
    await make_chunk(
        session,
        interno_paper,
        is_headline=True,
        body_text="Paper interno sobre redes neuronales.",
    )
    await session.commit()

    r = await client.get(
        "/api/search",
        params=[("q", "redes neuronales"), ("tipo", "tesis")],
    )
    assert r.status_code == 200
    data = r.json()
    assert {row["doc_id"] for row in data["results"]} == {publico_tesis}
    assert data["total"] == 1
    assert data["unfiltered_total"] == 2
    assert data["unfiltered_total"] >= data["total"]
