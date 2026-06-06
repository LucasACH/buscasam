"""search_events impression logging + search_clicks attribution (core/search_log)."""

import httpx
import numpy as np
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from buscasam.api.app import create_app
from buscasam.api.deps import get_session, get_tei_client
from tests.factories import make_chunk, make_document


def _tei_5xx_transport() -> httpx.MockTransport:
    return httpx.MockTransport(lambda req: httpx.Response(503, text="tei down"))


def _tei_healthy_transport(vec: np.ndarray) -> httpx.MockTransport:
    return httpx.MockTransport(lambda req: httpx.Response(200, json=[vec.tolist()]))


def _build_client(session, transport: httpx.MockTransport):
    tei = httpx.AsyncClient(transport=transport, base_url="http://tei")

    async def _session_override():
        yield session

    async def _tei_override():
        return tei

    app = create_app()
    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_tei_client] = _tei_override
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test"), tei


@pytest_asyncio.fixture
async def client(session):
    c, tei = _build_client(session, _tei_5xx_transport())
    async with c:
        yield c
    await tei.aclose()


@pytest_asyncio.fixture
async def hybrid_client(session):
    v = np.zeros(1024, dtype=np.float16)
    v[0] = 1.0
    c, tei = _build_client(session, _tei_healthy_transport(v))
    async with c:
        yield c
    await tei.aclose()


async def _seed_doc(session) -> int:
    doc_id = await make_document(
        session,
        titulo="Búsqueda léxica vía API",
        abstract="Documento público sobre búsqueda léxica vía API.",
    )
    await make_chunk(
        session, doc_id, is_headline=True, body_text="Búsqueda léxica vía API."
    )
    await session.commit()
    return doc_id


async def test_relevance_search_records_impression(client, session):
    doc_id = await _seed_doc(session)

    r = await client.get("/api/search", params={"q": "búsqueda léxica"})
    assert r.status_code == 200
    search_id = r.json()["search_id"]
    assert search_id

    row = (
        await session.execute(
            text(
                "SELECT q, q_norm, doc_ids, total, lexical_fallback, "
                "semantic_used, pagina FROM search_events WHERE search_id = :s"
            ),
            {"s": search_id},
        )
    ).one()
    assert row.q == "búsqueda léxica"
    assert row.q_norm == "búsqueda léxica"
    assert row.doc_ids == [doc_id]
    assert row.total == 1
    assert row.pagina == 1
    # `client` fixture serves TEI 5xx → lexical-only fallback, no semantic side.
    assert row.lexical_fallback is True
    assert row.semantic_used is False


async def test_semantic_search_marks_semantic_used(hybrid_client, session):
    await _seed_doc(session)

    r = await hybrid_client.get("/api/search", params={"q": "búsqueda léxica"})
    search_id = r.json()["search_id"]

    used = (
        await session.execute(
            text("SELECT semantic_used FROM search_events WHERE search_id = :s"),
            {"s": search_id},
        )
    ).scalar_one()
    assert used is True


async def test_recientes_browse_logs_no_impression(client, session):
    await _seed_doc(session)

    r = await client.get("/api/search", params={"orden": "recientes"})
    assert r.status_code == 200
    assert r.json()["search_id"] is None

    count = (
        await session.execute(text("SELECT count(*) FROM search_events"))
    ).scalar_one()
    assert count == 0


async def test_click_endpoint_records_and_dedups(client, session):
    doc_id = await _seed_doc(session)
    search_id = (
        await client.get("/api/search", params={"q": "búsqueda léxica"})
    ).json()["search_id"]

    body = {"search_id": search_id, "doc_id": doc_id, "rank": 3}
    assert (await client.post("/api/search/click", json=body)).status_code == 204
    # Re-navigation / re-render must not double-count (rank is fixed per search).
    assert (await client.post("/api/search/click", json=body)).status_code == 204

    rows = (
        await session.execute(
            text("SELECT doc_id, rank FROM search_clicks WHERE search_id = :s"),
            {"s": search_id},
        )
    ).all()
    assert rows == [(doc_id, 3)]


async def test_click_rejected_when_doc_not_in_impression(client, session):
    doc_id = await _seed_doc(session)
    search_id = (
        await client.get("/api/search", params={"q": "búsqueda léxica"})
    ).json()["search_id"]

    # A doc never shown for this search, and an unknown search_id, must both be
    # gated out — the endpoint stays 204 (fire-and-forget) but nothing is stored.
    unseen = {"search_id": search_id, "doc_id": doc_id + 999, "rank": 1}
    forged = {"search_id": "deadbeef", "doc_id": doc_id, "rank": 1}
    assert (await client.post("/api/search/click", json=unseen)).status_code == 204
    assert (await client.post("/api/search/click", json=forged)).status_code == 204

    count = (
        await session.execute(text("SELECT count(*) FROM search_clicks"))
    ).scalar_one()
    assert count == 0
