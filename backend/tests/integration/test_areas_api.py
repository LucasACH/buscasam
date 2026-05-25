import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from buscasam.api.app import create_app
from buscasam.api.deps import get_session


@pytest_asyncio.fixture
async def client(session):
    async def _override():
        yield session

    app = create_app()
    app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_areas_endpoint_returns_full_tree(client, session):
    await session.execute(
        text(
            "INSERT INTO areas (area_path, display_name) VALUES "
            "('escuela_ciencia', 'Escuela de Ciencia y Tecnología'),"
            "('escuela_ciencia.carrera_informatica', 'Ing. Informática'),"
            "('escuela_ciencia.carrera_informatica.materia_bd', 'Bases de Datos'),"
            "('escuela_humanidades', 'Escuela de Humanidades')"
        )
    )
    await session.commit()

    r = await client.get("/api/areas")

    assert r.status_code == 200
    body = r.json()
    assert body == [
        {"area_path": "escuela_ciencia", "display_name": "Escuela de Ciencia y Tecnología"},
        {
            "area_path": "escuela_ciencia.carrera_informatica",
            "display_name": "Ing. Informática",
        },
        {
            "area_path": "escuela_ciencia.carrera_informatica.materia_bd",
            "display_name": "Bases de Datos",
        },
        {"area_path": "escuela_humanidades", "display_name": "Escuela de Humanidades"},
    ]
