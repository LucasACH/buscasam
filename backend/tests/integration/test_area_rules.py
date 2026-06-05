"""Integration tests for the per-tipo minimum area_path depth
(core/documents/area_rules): create rejects too-broad pairs at the schema
boundary; PATCH re-checks against the stored pair."""

from __future__ import annotations

import base64
import secrets

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from buscasam.api.app import create_app
from buscasam.api.deps import get_session
from buscasam.core import auth
from buscasam.settings import settings
from tests.factories import make_document, make_document_author, make_user

_ORIGIN = "http://localhost:3000"


@pytest_asyncio.fixture
async def client(session, monkeypatch):
    monkeypatch.setattr(settings, "secret_key", "test-secret")

    async def _session_override():
        yield session

    app = create_app()
    app.dependency_overrides[get_session] = _session_override
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


async def _seed_session(session, user_id: int) -> bytes:
    sid = secrets.token_bytes(32)
    await session.execute(
        text("INSERT INTO sessions (sid, user_id) VALUES (:sid, :uid)"),
        {"sid": sid, "uid": user_id},
    )
    return sid


def _sid_cookie(sid: bytes) -> str:
    return base64.urlsafe_b64encode(sid).rstrip(b"=").decode()


def _draft(document_type: str, area_path: str) -> dict:
    return {
        "title": "Trabajo de prueba",
        "area_path": area_path,
        "document_type": document_type,
        "visibility": "publico",
        "external_authors": [],
        "coauthor_user_ids": [],
    }


async def _post_draft(client, session, document_type: str, area_path: str):
    uid = await make_user(session)
    sid = await _seed_session(session, uid)
    await session.commit()
    return await client.post(
        "/api/documents",
        json=_draft(document_type, area_path),
        headers={"origin": _ORIGIN},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )


@pytest.mark.parametrize(
    ("document_type", "area_path"),
    [
        # Course-bound tipos need a materia.
        ("trabajo_practico", "escuela_ciencia.carrera_fisica"),
        ("apunte_resumen", "escuela_ciencia.area_exactas.carrera_fisica"),
        ("informe_catedra", "escuela_ciencia.area_exactas"),
        # Program-bound tipos need at least a carrera.
        ("tesis", "escuela_ciencia.area_exactas"),
        ("monografia", "escuela_ciencia"),
        # Discipline-bound tipos need at least an área; escuela never suffices.
        ("paper", "escuela_ciencia"),
        ("proyecto_investigacion", "escuela_ciencia"),
        ("ponencia_poster", "escuela_ciencia"),
        # Leaf segment without a recognized level prefix.
        ("paper", "escuela_ciencia.fisica"),
    ],
)
async def test_create_draft_area_too_broad_returns_422(
    client, session, document_type, area_path
):
    r = await _post_draft(client, session, document_type, area_path)
    assert r.status_code == 422


@pytest.mark.parametrize(
    ("document_type", "area_path"),
    [
        # At the minimum level.
        ("trabajo_practico", "escuela_ciencia.carrera_fisica.materia_mecanica"),
        ("tesis", "escuela_ciencia.carrera_fisica"),
        ("monografia", "escuela_ciencia.area_exactas.carrera_fisica"),
        ("paper", "escuela_ciencia.area_exactas"),
        # Deeper than the minimum is always allowed.
        ("tesis", "escuela_ciencia.carrera_fisica.materia_mecanica"),
        ("paper", "escuela_ciencia.carrera_fisica.materia_mecanica"),
    ],
)
async def test_create_draft_area_at_or_below_minimum_returns_201(
    client, session, document_type, area_path
):
    r = await _post_draft(client, session, document_type, area_path)
    assert r.status_code == 201

    stored = (
        await session.execute(
            text("SELECT area_path::text FROM documents WHERE id = :id"),
            {"id": r.json()["id"]},
        )
    ).scalar_one()
    assert stored == area_path


async def _seed_owned_doc(session, *, area_path: str, tipo: str) -> tuple[int, bytes]:
    uid = await make_user(session)
    sid = await _seed_session(session, uid)
    doc_id = await make_document(
        session, publication_status="draft", area_path=area_path, tipo=tipo
    )
    await make_document_author(session, doc_id, user_id=uid, status="owner")
    await session.commit()
    return doc_id, sid


async def test_patch_document_type_validates_against_stored_area(client, session):
    # Stored area is carrera-level: switching to a materia-bound tipo → 422.
    doc_id, sid = await _seed_owned_doc(
        session, area_path="escuela_ciencia.carrera_fisica", tipo="tesis"
    )

    r = await client.patch(
        f"/api/documents/{doc_id}",
        json={"document_type": "apunte_resumen"},
        headers={"origin": settings.base_url},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 422
    tipo = (
        await session.execute(
            text("SELECT tipo FROM documents WHERE id = :id"), {"id": doc_id}
        )
    ).scalar_one()
    assert tipo == "tesis"


async def test_patch_area_path_validates_against_stored_tipo(client, session):
    # Stored tipo is materia-bound: broadening the area to carrera level → 422,
    # while a sibling materia is fine.
    doc_id, sid = await _seed_owned_doc(
        session,
        area_path="escuela_ciencia.carrera_fisica.materia_mecanica",
        tipo="trabajo_practico",
    )

    r = await client.patch(
        f"/api/documents/{doc_id}",
        json={"area_path": "escuela_ciencia.carrera_fisica"},
        headers={"origin": settings.base_url},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )
    assert r.status_code == 422

    r = await client.patch(
        f"/api/documents/{doc_id}",
        json={"area_path": "escuela_ciencia.carrera_fisica.materia_optica"},
        headers={"origin": settings.base_url},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )
    assert r.status_code == 204
