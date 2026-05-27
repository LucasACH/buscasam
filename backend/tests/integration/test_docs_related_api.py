"""Integration tests for GET /api/docs/{id}/related (issue #45)."""
from __future__ import annotations

import base64
import secrets
from datetime import date

import numpy as np
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from buscasam.api.app import create_app
from buscasam.api.deps import get_session
from buscasam.settings import settings
from tests.factories import (
    make_chunk,
    make_document,
    make_document_author,
    make_user,
)


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


async def _sid_cookie(session, user_id: int) -> str:
    sid = secrets.token_bytes(32)
    await session.execute(
        text("INSERT INTO sessions (sid, user_id) VALUES (:sid, :uid)"),
        {"sid": sid, "uid": user_id},
    )
    return base64.urlsafe_b64encode(sid).rstrip(b"=").decode()


async def _seed_current_version(session, doc_id: int) -> None:
    await session.execute(
        text(
            "INSERT INTO document_versions "
            "(doc_id, version_no, sha256, original_filename, bytes, mime, "
            " index_status, is_current) "
            "VALUES (:d, 1, decode(repeat('22', 32), 'hex'), 'f.pdf', 1, "
            " 'application/pdf', 'indexed', true)"
        ),
        {"d": doc_id},
    )


def _vec(seed: float) -> np.ndarray:
    v = np.full(1024, 0.001, dtype=np.float16)
    v[0] = seed
    norm = np.linalg.norm(v.astype(np.float32))
    return (v.astype(np.float32) / norm).astype(np.float16)


async def _add_headline(session, doc_id: int, embedding: np.ndarray) -> None:
    await make_chunk(
        session,
        doc_id,
        chunk_seq=0,
        is_headline=True,
        body_text=f"headline {doc_id}",
        embedding=embedding,
    )


async def test_returns_200_with_related_list_for_invitado(client, session):
    source_id = await make_document(session, visibility="publico", titulo="src")
    await _seed_current_version(session, source_id)
    await _add_headline(session, source_id, _vec(1.0))

    sibling_id = await make_document(
        session,
        visibility="publico",
        titulo="Sibling",
        area_path="escuela_ciencia",
        tipo="paper",
        fecha=date(2024, 1, 15),
    )
    await _seed_current_version(session, sibling_id)
    await _add_headline(session, sibling_id, _vec(1.0))
    author_id = await make_user(session, name="Ada")
    await make_document_author(
        session, sibling_id, user_id=author_id, status="owner", display_name="Ada"
    )
    await session.commit()

    r = await client.get(f"/api/docs/{source_id}/related")

    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    row = body[0]
    assert row["doc_id"] == sibling_id
    assert row["titulo"] == "Sibling"
    assert row["area_path"] == "escuela_ciencia"
    assert row["tipo"] == "paper"
    assert row["fecha"] == "2024-01-15"
    assert row["autores"] == [{"display_name": "Ada", "user_id": author_id}]
    assert 0.78 <= row["similarity"] <= 1.0


@pytest.mark.parametrize(
    "factory_kwargs",
    [
        {"visibility": "interno"},
        {"visibility": "privado"},
        {"publication_status": "draft"},
        {"soft_deleted": True},
        {"moderation_hidden": True},
    ],
    ids=["interno", "privado", "draft", "soft_deleted", "moderation_hidden"],
)
async def test_returns_404_with_uniform_envelope_for_unreadable_source(
    client, session, factory_kwargs
):
    source_id = await make_document(session, **factory_kwargs)
    await _seed_current_version(session, source_id)
    await _add_headline(session, source_id, _vec(1.0))
    await session.commit()

    r = await client.get(f"/api/docs/{source_id}/related")

    assert r.status_code == 404
    assert "login" not in r.text.lower()
    assert "rol" not in r.text.lower()


async def test_returns_404_for_non_existent_id(client, session):
    await session.commit()
    r = await client.get("/api/docs/999999/related")
    assert r.status_code == 404


async def test_returns_empty_array_when_source_readable_with_no_neighbours(
    client, session
):
    """No similar neighbours above the floor → 200 with []."""
    source_id = await make_document(session, visibility="publico", titulo="lonely")
    await _seed_current_version(session, source_id)
    await _add_headline(session, source_id, _vec(1.0))
    await session.commit()

    r = await client.get(f"/api/docs/{source_id}/related")

    assert r.status_code == 200
    assert r.json() == []


async def test_estudiante_sees_interno_neighbour_invitado_does_not(client, session):
    """Cross-role: rail respects readable_where for candidates."""
    source_id = await make_document(session, visibility="publico", titulo="src")
    await _seed_current_version(session, source_id)
    await _add_headline(session, source_id, _vec(1.0))

    interno_id = await make_document(session, visibility="interno", titulo="int")
    await _seed_current_version(session, interno_id)
    await _add_headline(session, interno_id, _vec(1.0))

    estudiante_id = await make_user(session, name="Est")
    sid = await _sid_cookie(session, estudiante_id)
    await session.commit()

    invitado = await client.get(f"/api/docs/{source_id}/related")
    estudiante = await client.get(
        f"/api/docs/{source_id}/related", cookies={"sid": sid}
    )

    assert {row["doc_id"] for row in invitado.json()} == set()
    assert {row["doc_id"] for row in estudiante.json()} == {interno_id}
