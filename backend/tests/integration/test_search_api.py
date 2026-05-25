from datetime import date

import httpx
import numpy as np
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from buscasam.api.app import create_app
from buscasam.api.deps import get_session, get_tei_client
from tests.factories import make_chunk, make_document


def _tei_5xx_transport() -> httpx.MockTransport:
    return httpx.MockTransport(lambda req: httpx.Response(503, text="tei down"))


def _tei_healthy_transport(vec: np.ndarray) -> httpx.MockTransport:
    return httpx.MockTransport(
        lambda req: httpx.Response(200, json=[vec.tolist()])
    )


def _unit(dim: int) -> np.ndarray:
    v = np.zeros(1024, dtype=np.float16)
    v[dim] = 1.0
    return v


def _build_client(session, transport: httpx.MockTransport):
    tei = httpx.AsyncClient(transport=transport, base_url="http://tei")

    async def _session_override():
        yield session

    async def _tei_override():
        return tei

    app = create_app()
    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_tei_client] = _tei_override
    asgi = ASGITransport(app=app)
    return AsyncClient(transport=asgi, base_url="http://test"), tei


@pytest_asyncio.fixture
async def client(session):
    c, tei = _build_client(session, _tei_5xx_transport())
    async with c:
        yield c
    await tei.aclose()


@pytest_asyncio.fixture
async def hybrid_client(session):
    c, tei = _build_client(session, _tei_healthy_transport(_unit(0)))
    async with c:
        yield c
    await tei.aclose()


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


async def test_search_endpoint_hybrid_surfaces_pure_semantic_hit(hybrid_client, session):
    """TEI healthy → query with no lexical overlap surfaces a semantically-similar doc."""
    sem_id = await make_document(
        session,
        titulo="Documento sobre física cuántica",
        abstract="Estudio sobre partículas subatómicas y su comportamiento.",
    )
    await make_chunk(
        session,
        sem_id,
        is_headline=True,
        body_text="Sin coincidencia textual con la consulta.",
        embedding=_unit(0),
    )
    await session.commit()

    r = await hybrid_client.get("/api/search", params={"q": "zorgblat"})

    assert r.status_code == 200
    data = r.json()
    assert data["lexical_fallback"] is False
    assert [row["doc_id"] for row in data["results"]] == [sem_id]
    assert data["results"][0]["snippet"] == (
        "Estudio sobre partículas subatómicas y su comportamiento."
    )


async def test_search_endpoint_falls_back_to_lexical_on_tei_5xx(client, session):
    """TEI 5xx → results still return (lexical-only) + lexical_fallback_rate log."""
    import logging

    publico_id = await make_document(
        session,
        titulo="Redes neuronales en producción",
        abstract="Estudio sobre redes neuronales en producción.",
    )
    await make_chunk(
        session,
        publico_id,
        is_headline=True,
        body_text="Redes neuronales en producción.",
    )
    await session.commit()

    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Capture(level=logging.INFO)
    search_logger = logging.getLogger("buscasam.search")
    search_logger.addHandler(handler)
    search_logger.setLevel(logging.INFO)
    try:
        r = await client.get("/api/search", params={"q": "redes neuronales"})
    finally:
        search_logger.removeHandler(handler)

    assert r.status_code == 200
    data = r.json()
    assert [row["doc_id"] for row in data["results"]] == [publico_id]
    assert data["total"] == 1

    fallback_records = [rec for rec in records if rec.message == "lexical_fallback_rate"]
    assert fallback_records, "expected at least one lexical_fallback_rate log line"
    assert any(getattr(rec, "fallback", False) is True for rec in fallback_records)


async def test_search_endpoint_recientes_orders_by_fecha_desc(client, session):
    """orden=recientes returns matching docs sorted fecha desc with exact total."""
    old_id = await make_document(
        session,
        titulo="Estudio antiguo sobre redes",
        abstract="Documento antiguo.",
        fecha=date(2019, 1, 1),
    )
    await make_chunk(
        session, old_id, is_headline=True, body_text="Estudio antiguo sobre redes."
    )

    new_id = await make_document(
        session,
        titulo="Estudio reciente sobre redes",
        abstract="Documento reciente.",
        fecha=date(2024, 1, 1),
    )
    await make_chunk(
        session, new_id, is_headline=True, body_text="Estudio reciente sobre redes."
    )
    await session.commit()

    r = await client.get("/api/search", params={"q": "redes", "orden": "recientes"})
    assert r.status_code == 200
    data = r.json()
    assert [row["doc_id"] for row in data["results"]] == [new_id, old_id]
    assert data["total"] == 2
    assert data["saturated"] is False


async def test_search_endpoint_recientes_allows_empty_q_browse(client, session):
    """orden=recientes with empty q returns the público corpus sorted fecha desc."""
    a_id = await make_document(
        session,
        titulo="Doc A",
        abstract="A",
        fecha=date(2020, 1, 1),
    )
    await make_chunk(session, a_id, is_headline=True, body_text="Doc A cuerpo.")
    b_id = await make_document(
        session,
        titulo="Doc B",
        abstract="B",
        fecha=date(2023, 1, 1),
    )
    await make_chunk(session, b_id, is_headline=True, body_text="Doc B cuerpo.")
    await session.commit()

    r = await client.get("/api/search", params={"orden": "recientes"})
    assert r.status_code == 200
    data = r.json()
    assert [row["doc_id"] for row in data["results"]] == [b_id, a_id]
    assert data["total"] == 2


async def test_search_endpoint_rejects_empty_q_under_relevancia(client):
    """Empty q with orden=relevancia (or default) is rejected with 422."""
    r_default = await client.get("/api/search")
    assert r_default.status_code == 422

    r_explicit = await client.get("/api/search", params={"orden": "relevancia"})
    assert r_explicit.status_code == 422


async def test_search_endpoint_recientes_accepts_pagina_over_20(client, session):
    """Under orden=recientes, pagina>20 is accepted."""
    doc_id = await make_document(session, titulo="Doc", abstract="Doc")
    await make_chunk(session, doc_id, is_headline=True, body_text="Doc cuerpo.")
    await session.commit()

    r = await client.get(
        "/api/search", params={"orden": "recientes", "pagina": 21}
    )
    assert r.status_code == 200
    assert r.json()["results"] == []
    assert r.json()["total"] == 1


async def test_search_endpoint_rejects_unknown_orden(client):
    r = await client.get("/api/search", params={"q": "anything", "orden": "popular"})
    assert r.status_code == 422


async def test_search_endpoint_unfiltered_total_when_paginated_past_end(client, session):
    """unfiltered_total reports the true count even when pagina is past the result set."""
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
    await session.commit()

    r = await client.get(
        "/api/search",
        params=[("q", "redes neuronales"), ("tipo", "tesis"), ("pagina", "2")],
    )
    assert r.status_code == 200
    data = r.json()
    assert data["results"] == []
    assert data["total"] == 0
    assert data["unfiltered_total"] == 1
