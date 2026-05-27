"""Integration tests for api/documents (GET /api/me/documents)."""
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
from buscasam.core.chunk import headline_fingerprint
from buscasam.settings import settings
from tests.factories import make_document, make_document_author, make_user


async def _seed_candidate(
    session,
    *,
    owner_id: int,
    titulo: str = "Tesis",
    index_status: str = "indexed",
    staged_abstract: str = "resumen",
) -> tuple[int, int]:
    """Returns (doc_id, version_id) for a draft owned by owner_id."""
    doc_id = await make_document(
        session, publication_status="draft", titulo=titulo
    )
    await make_document_author(session, doc_id, user_id=owner_id, status="owner")
    fp = headline_fingerprint(titulo, staged_abstract)
    version_id = (
        await session.execute(
            text(
                "INSERT INTO document_versions "
                "(doc_id, version_no, sha256, original_filename, bytes, mime, "
                " uploaded_by, index_status, staged_abstract, headline_fingerprint) "
                "VALUES (:d, 1, decode(repeat('00', 32), 'hex'), 'f', 1, "
                " 'application/pdf', :u, :st, :abs, :fp) RETURNING id"
            ),
            {
                "d": doc_id,
                "u": owner_id,
                "st": index_status,
                "abs": staged_abstract,
                "fp": fp,
            },
        )
    ).scalar_one()
    return doc_id, version_id


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
        text(
            "INSERT INTO sessions (sid, user_id) "
            "VALUES (:sid, :uid)"
        ),
        {"sid": sid, "uid": user_id},
    )
    return sid


def _sid_cookie(sid: bytes) -> str:
    return base64.urlsafe_b64encode(sid).rstrip(b"=").decode()


async def test_list_own_documents_empty_for_authenticated_user(client, session):
    uid = await make_user(session)
    sid = await _seed_session(session, uid)
    await session.commit()

    r = await client.get(
        "/api/me/documents",
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 200
    assert r.json() == []


async def test_list_own_documents_returns_401_for_invitado(client):
    r = await client.get("/api/me/documents")
    assert r.status_code == 401


async def test_get_draft_returns_state_for_owner(client, session):
    uid = await make_user(session)
    sid = await _seed_session(session, uid)
    doc_id, version_id = await _seed_candidate(session, owner_id=uid)
    await session.commit()

    r = await client.get(
        f"/api/documents/{doc_id}/draft",
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "Tesis"
    assert body["index_status"] == "indexed"
    assert body["publish_gate_reason"] is None
    assert body["staged_abstract"] == "resumen"


async def test_get_draft_cross_user_returns_404(client, session):
    owner = await make_user(session)
    other = await make_user(session)
    sid = await _seed_session(session, other)
    doc_id, version_id = await _seed_candidate(session, owner_id=owner)
    await session.commit()

    r = await client.get(
        f"/api/documents/{doc_id}/draft",
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 404


async def test_patch_draft_persists_metadata(client, session):
    uid = await make_user(session)
    sid = await _seed_session(session, uid)
    doc_id, version_id = await _seed_candidate(session, owner_id=uid)
    await session.commit()

    r = await client.patch(
        f"/api/documents/{doc_id}",
        json={"keywords": ["redes", "grafos"]},
        headers={"origin": settings.base_url},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 204
    staged = (
        await session.execute(
            text("SELECT staged_keywords FROM document_versions WHERE id = :id"),
            {"id": version_id},
        )
    ).scalar_one()
    assert staged == ["redes", "grafos"]


async def test_patch_draft_persists_document_fields(client, session):
    uid = await make_user(session)
    sid = await _seed_session(session, uid)
    doc_id, version_id = await _seed_candidate(session, owner_id=uid)
    await session.commit()

    r = await client.patch(
        f"/api/documents/{doc_id}",
        json={
            "visibility": "interno",
            "area_path": "escuela.fisica",
            "document_type": "paper",
        },
        headers={"origin": settings.base_url},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 204
    row = (
        await session.execute(
            text(
                "SELECT visibility, area_path::text AS area_path, tipo "
                "FROM documents WHERE id = :id"
            ),
            {"id": doc_id},
        )
    ).mappings().one()
    assert row["visibility"] == "interno"
    assert row["area_path"] == "escuela.fisica"
    assert row["tipo"] == "paper"


async def test_patch_draft_clears_fecha_with_null(client, session):
    uid = await make_user(session)
    sid = await _seed_session(session, uid)
    doc_id, version_id = await _seed_candidate(session, owner_id=uid)
    await session.execute(
        text("UPDATE document_versions SET staged_fecha = '2020-01-01' WHERE id = :id"),
        {"id": version_id},
    )
    await session.commit()

    r = await client.patch(
        f"/api/documents/{doc_id}",
        json={"fecha": None},
        headers={"origin": settings.base_url},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 204
    staged = (
        await session.execute(
            text("SELECT staged_fecha FROM document_versions WHERE id = :id"),
            {"id": version_id},
        )
    ).scalar_one()
    assert staged is None


@pytest.mark.parametrize(
    "body",
    [
        {"visibility": "secreto"},
        {"document_type": "blogpost"},
        {"area_path": "Escuela.Física"},
    ],
)
async def test_patch_draft_invalid_enum_or_path_returns_422(client, session, body):
    uid = await make_user(session)
    sid = await _seed_session(session, uid)
    doc_id, version_id = await _seed_candidate(session, owner_id=uid)
    await session.commit()

    r = await client.patch(
        f"/api/documents/{doc_id}",
        json=body,
        headers={"origin": settings.base_url},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 422


async def test_patch_draft_cross_user_returns_404(client, session):
    owner = await make_user(session)
    other = await make_user(session)
    sid = await _seed_session(session, other)
    doc_id, version_id = await _seed_candidate(session, owner_id=owner)
    await session.commit()

    r = await client.patch(
        f"/api/documents/{doc_id}",
        json={"title": "Hijack"},
        headers={"origin": settings.base_url},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 404
    titulo = (
        await session.execute(
            text("SELECT titulo FROM documents WHERE id = :id"), {"id": doc_id}
        )
    ).scalar_one()
    assert titulo == "Tesis"
