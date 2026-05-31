"""Integration tests for read recording + GET /api/docs/popular (issue #109)."""

from __future__ import annotations

import base64
import secrets
from datetime import date

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from buscasam.api.app import create_app
from buscasam.api.deps import get_session
from buscasam.settings import settings
from tests.factories import make_document, make_document_author, make_user


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
            " index_status, is_current, first_published_at) "
            "VALUES (:d, 1, decode(:sha, 'hex'), 'f.pdf', 2048, 'application/pdf', "
            "        'indexed', true, now())"
        ),
        {"d": doc_id, "sha": "ab" * 32},
    )


async def _reads_count(session, doc_id: int) -> int:
    return (
        await session.execute(
            text("SELECT count(*) FROM document_reads WHERE doc_id = :d"),
            {"d": doc_id},
        )
    ).scalar_one()


async def test_detail_open_records_one_read(client, session):
    doc_id = await make_document(session, visibility="publico")
    await _seed_current_version(session, doc_id)
    user_id = await make_user(session)
    sid = await _sid_cookie(session, user_id)
    await session.commit()

    r = await client.get(f"/api/docs/{doc_id}", cookies={"sid": sid})

    assert r.status_code == 200
    assert await _reads_count(session, doc_id) == 1


async def test_same_reader_same_day_does_not_double_count(client, session):
    doc_id = await make_document(session, visibility="publico")
    await _seed_current_version(session, doc_id)
    user_id = await make_user(session)
    sid = await _sid_cookie(session, user_id)
    await session.commit()

    await client.get(f"/api/docs/{doc_id}", cookies={"sid": sid})
    await client.get(f"/api/docs/{doc_id}", cookies={"sid": sid})

    assert await _reads_count(session, doc_id) == 1


async def test_invitado_gets_rid_cookie_and_repeat_does_not_double_count(
    client, session
):
    doc_id = await make_document(session, visibility="publico")
    await _seed_current_version(session, doc_id)
    await session.commit()

    r1 = await client.get(f"/api/docs/{doc_id}")
    rid = r1.cookies.get("rid")
    assert rid is not None
    r2 = await client.get(f"/api/docs/{doc_id}", cookies={"rid": rid})

    assert r2.status_code == 200
    assert await _reads_count(session, doc_id) == 1


async def test_minimal_invite_records_no_read(client, session):
    doc_id = await make_document(session, visibility="privado")
    await _seed_current_version(session, doc_id)
    owner_id = await make_user(session)
    pending_id = await make_user(session)
    await make_document_author(session, doc_id, user_id=owner_id, status="owner")
    await make_document_author(
        session, doc_id, user_id=pending_id, status="pending", display_name="P"
    )
    sid = await _sid_cookie(session, pending_id)
    await session.commit()

    r = await client.get(f"/api/docs/{doc_id}", cookies={"sid": sid})

    assert r.json()["view"] == "minimal"
    assert await _reads_count(session, doc_id) == 0


async def test_download_records_no_read(client, session):
    doc_id = await make_document(session, visibility="publico")
    await _seed_current_version(session, doc_id)
    await session.commit()

    await client.get(f"/api/docs/{doc_id}/download")

    assert await _reads_count(session, doc_id) == 0


async def test_not_found_records_no_read(client, session):
    doc_id = await make_document(session, visibility="privado")
    await _seed_current_version(session, doc_id)
    await session.commit()

    r = await client.get(f"/api/docs/{doc_id}")  # invitado → 404

    assert r.status_code == 404
    assert await _reads_count(session, doc_id) == 0


async def _seed_reads(session, doc_id: int, readers: int) -> None:
    for i in range(readers):
        await session.execute(
            text(
                "INSERT INTO document_reads (doc_id, reader_key, read_day) "
                "VALUES (:d, :k, CURRENT_DATE)"
            ),
            {"d": doc_id, "k": f"u:{doc_id}:{i}"},
        )


async def test_popular_returns_ranking_and_public_total(client, session):
    hot = await make_document(
        session,
        visibility="publico",
        titulo="Hot",
        area_path="escuela_ciencia",
        tipo="tesis",
        fecha=date(2024, 3, 1),
    )
    warm = await make_document(session, visibility="publico", titulo="Warm")
    await make_document(session, visibility="publico", titulo="Cold")  # no reads
    interno = await make_document(session, visibility="interno", titulo="Int")
    await _seed_reads(session, hot, 3)
    await _seed_reads(session, warm, 1)
    await _seed_reads(session, interno, 9)  # excluded though more-read
    await session.commit()

    r = await client.get("/api/docs/popular?window=week&limit=3")

    assert r.status_code == 200
    body = r.json()
    assert [x["doc_id"] for x in body["results"]] == [hot, warm]
    assert body["results"][0] == {
        "doc_id": hot,
        "titulo": "Hot",
        "area_path": "escuela_ciencia",
        "tipo": "tesis",
        "fecha": "2024-03-01",
        "reads": 3,
    }
    assert body["public_total"] == 3  # hot, warm, cold (interno excluded)


async def test_popular_caps_limit(client, session):
    for _ in range(25):
        doc_id = await make_document(session, visibility="publico")
        await _seed_reads(session, doc_id, 1)
    await session.commit()

    r = await client.get("/api/docs/popular?window=week&limit=100")

    assert r.status_code == 200
    assert len(r.json()["results"]) == 20
