"""Integration tests for api/moderation report-scoped inspection (issue #77,
module map §api/moderation).

require_docente gates both reads; the report-scoped predicate
(moderation_inspection_where) lets a Docente inspect the document behind a
specific report — even privado/interno/hidden — without standing access to
private documents. Every miss (unknown report, author-soft-deleted doc, no
current version) maps to a uniform 404; non-Docente → 403.
"""
from __future__ import annotations

import base64
import secrets

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.api.app import create_app
from buscasam.api.deps import get_session
from buscasam.settings import settings
from tests.factories import make_document, make_document_author, make_user

ORIGIN = settings.base_url


@pytest_asyncio.fixture
async def client(session):
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


def _headers(cookie: str) -> dict:
    return {"cookie": f"sid={cookie}", "origin": ORIGIN}


async def _file_report(
    session: AsyncSession, doc_id: int, *, reporter: int, status: str = "open"
) -> int:
    return (
        await session.execute(
            text(
                "INSERT INTO document_reports (doc_id, reporter_user_id, reason, status) "
                "VALUES (:d, :u, 'spam', :st) RETURNING id"
            ),
            {"d": doc_id, "u": reporter, "st": status},
        )
    ).scalar_one()


async def _seed_current_version(
    session: AsyncSession,
    doc_id: int,
    *,
    original_filename: str = "tesis.pdf",
    mime: str = "application/pdf",
    sha_hex: str = "aa" * 32,
) -> None:
    await session.execute(
        text(
            "INSERT INTO document_versions "
            "(doc_id, version_no, sha256, original_filename, bytes, mime, "
            " index_status, is_current, first_published_at) "
            "VALUES (:d, 1, decode(:sha, 'hex'), :name, 2048, :m, 'indexed', true, now())"
        ),
        {"d": doc_id, "sha": sha_hex, "name": original_filename, "m": mime},
    )


async def _docente_cookie(session) -> str:
    docente = await make_user(session, role="docente")
    return await _sid_cookie(session, docente)


async def test_document_returns_metadata_for_privado_reported_doc(client, session):
    doc_id = await make_document(
        session,
        visibility="privado",
        titulo="Secreto",
        abstract="resumen",
        tipo="tesis",
        area_path="escuela_ciencia.matematica",
    )
    await session.execute(
        text("UPDATE documents SET keywords = ARRAY['algebra', 'topologia'] WHERE id = :d"),
        {"d": doc_id},
    )
    author_user_id = await make_user(session)
    await make_document_author(
        session, doc_id, user_id=author_user_id, status="owner",
        display_name="Ana",
    )
    reporter = await make_user(session)
    report_id = await _file_report(session, doc_id, reporter=reporter)
    cookie = await _docente_cookie(session)

    r = await client.get(
        f"/api/moderation/reports/{report_id}/document", headers=_headers(cookie)
    )

    assert r.status_code == 200
    body = r.json()
    assert body["titulo"] == "Secreto"
    assert body["abstract"] == "resumen"
    assert body["tipo"] == "tesis"
    assert body["area_path"] == "escuela_ciencia.matematica"
    assert body["palabras_clave"] == ["algebra", "topologia"]
    assert body["autores"] == [{"display_name": "Ana", "user_id": author_user_id}]


@pytest.mark.parametrize("status", ["open", "resolved"])
async def test_document_works_for_open_and_resolved(client, session, status):
    doc_id = await make_document(session, visibility="interno", titulo="T")
    reporter = await make_user(session)
    report_id = await _file_report(session, doc_id, reporter=reporter, status=status)
    cookie = await _docente_cookie(session)

    r = await client.get(
        f"/api/moderation/reports/{report_id}/document", headers=_headers(cookie)
    )

    assert r.status_code == 200
    body = r.json()
    assert body["titulo"] == "T"
    assert body["palabras_clave"] == []  # COALESCE(keywords, ARRAY[]) for the null case


async def test_download_streams_current_main_file(client, session):
    doc_id = await make_document(session, visibility="privado")
    await _seed_current_version(
        session, doc_id, original_filename="hidden.pdf", sha_hex="cd" * 32
    )
    reporter = await make_user(session)
    report_id = await _file_report(session, doc_id, reporter=reporter)
    cookie = await _docente_cookie(session)

    r = await client.get(
        f"/api/moderation/reports/{report_id}/download", headers=_headers(cookie)
    )

    assert r.status_code == 200
    assert r.headers["X-Accel-Redirect"].endswith("cd" * 32)
    assert r.headers["Content-Type"] == "application/pdf"
    assert "hidden.pdf" in r.headers["Content-Disposition"]


@pytest.mark.parametrize("endpoint", ["document", "download"])
async def test_author_soft_deleted_doc_returns_404(client, session, endpoint):
    doc_id = await make_document(session, visibility="publico", soft_deleted=True)
    await _seed_current_version(session, doc_id)
    reporter = await make_user(session)
    report_id = await _file_report(session, doc_id, reporter=reporter)
    cookie = await _docente_cookie(session)

    r = await client.get(
        f"/api/moderation/reports/{report_id}/{endpoint}", headers=_headers(cookie)
    )

    assert r.status_code == 404


@pytest.mark.parametrize("endpoint", ["document", "download"])
async def test_unknown_report_id_returns_404(client, session, endpoint):
    cookie = await _docente_cookie(session)

    r = await client.get(
        f"/api/moderation/reports/999999/{endpoint}", headers=_headers(cookie)
    )

    assert r.status_code == 404


async def test_download_without_current_version_returns_404(client, session):
    doc_id = await make_document(session, visibility="privado")
    reporter = await make_user(session)
    report_id = await _file_report(session, doc_id, reporter=reporter)
    cookie = await _docente_cookie(session)

    r = await client.get(
        f"/api/moderation/reports/{report_id}/download", headers=_headers(cookie)
    )

    assert r.status_code == 404


@pytest.mark.parametrize("endpoint", ["document", "download"])
async def test_non_docente_returns_403(client, session, endpoint):
    doc_id = await make_document(session, visibility="publico")
    await _seed_current_version(session, doc_id)
    reporter = await make_user(session)
    report_id = await _file_report(session, doc_id, reporter=reporter)
    estudiante = await make_user(session, role="estudiante")
    cookie = await _sid_cookie(session, estudiante)

    r = await client.get(
        f"/api/moderation/reports/{report_id}/{endpoint}", headers=_headers(cookie)
    )

    assert r.status_code == 403


@pytest.mark.parametrize("endpoint", ["document", "download"])
async def test_unauthenticated_returns_401(client, session, endpoint):
    doc_id = await make_document(session, visibility="publico")
    reporter = await make_user(session)
    report_id = await _file_report(session, doc_id, reporter=reporter)
    await session.commit()

    r = await client.get(f"/api/moderation/reports/{report_id}/{endpoint}")

    assert r.status_code == 401
