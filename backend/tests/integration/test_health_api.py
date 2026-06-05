import pytest_asyncio
from httpx import ASGITransport, AsyncClient, MockTransport, Request, Response
from sqlalchemy import text

from buscasam.api.app import create_app
from buscasam.api.deps import get_session, get_tei_client


def _make_client(session, tei_handler):
    async def _override_session():
        yield session

    tei = AsyncClient(transport=MockTransport(tei_handler), base_url="http://tei")

    async def _override_tei():
        return tei

    app = create_app()
    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_tei_client] = _override_tei
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test"), tei


def _tei_ok(request: Request) -> Response:
    return Response(200, json={})


def _tei_down(request: Request) -> Response:
    return Response(503, text="unhealthy")


@pytest_asyncio.fixture
async def client(session):
    c, tei = _make_client(session, _tei_ok)
    async with c:
        yield c
    await tei.aclose()


async def test_health_all_ok_with_live_worker(client, session):
    await session.execute(
        text("INSERT INTO procrastinate_workers (last_heartbeat) VALUES (now())")
    )
    await session.commit()

    r = await client.get("/api/health")

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    keys = {s["key"] for s in body["services"]}
    assert keys == {"database", "embeddings", "workers", "metadata_llm"}
    workers = next(s for s in body["services"] if s["key"] == "workers")
    assert workers["status"] == "ok"
    assert "1 activo(s)" in workers["detail"]
    # metadata LLM is off by default — neutral "disabled", never drags overall.
    llm = next(s for s in body["services"] if s["key"] == "metadata_llm")
    assert llm["status"] == "disabled"


async def test_health_degraded_without_live_worker(client):
    r = await client.get("/api/health")

    body = r.json()
    workers = next(s for s in body["services"] if s["key"] == "workers")
    assert workers["status"] == "degraded"
    assert body["status"] == "degraded"


async def test_health_down_when_embeddings_unreachable(session):
    c, tei = _make_client(session, _tei_down)
    async with c:
        r = await c.get("/api/health")
    await tei.aclose()

    body = r.json()
    embeddings = next(s for s in body["services"] if s["key"] == "embeddings")
    assert embeddings["status"] == "down"
    assert body["status"] == "down"
