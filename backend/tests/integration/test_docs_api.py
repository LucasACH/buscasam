"""Integration tests for api/docs (reader endpoints, issue #43)."""
from __future__ import annotations

import base64
import secrets
from datetime import date
from urllib.parse import quote

import pytest
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


async def _seed_current_version(
    session,
    doc_id: int,
    *,
    original_filename: str = "tesis.pdf",
    bytes_: int = 2048,
    mime: str = "application/pdf",
    sha_hex: str = "ab" * 32,
) -> None:
    await session.execute(
        text(
            "INSERT INTO document_versions "
            "(doc_id, version_no, sha256, original_filename, bytes, mime, "
            " index_status, is_current) "
            "VALUES (:d, 1, decode(:sha, 'hex'), :name, :b, :m, 'indexed', true)"
        ),
        {"d": doc_id, "sha": sha_hex, "name": original_filename, "b": bytes_, "m": mime},
    )


async def _seed_attachment(
    session,
    doc_id: int,
    *,
    original_filename: str = "datos.csv",
    bytes_: int = 512,
    mime: str | None = "text/csv",
    sha_hex: str = "cd" * 32,
) -> int:
    return (
        await session.execute(
            text(
                "INSERT INTO document_attachments "
                "(doc_id, sha256, original_filename, bytes, mime) "
                "VALUES (:d, decode(:sha, 'hex'), :name, :b, :m) RETURNING id"
            ),
            {"d": doc_id, "sha": sha_hex, "name": original_filename, "b": bytes_, "m": mime},
        )
    ).scalar_one()


async def test_get_doc_detail_publico_returns_200_for_invitado(client, session):
    doc_id = await make_document(
        session,
        visibility="publico",
        titulo="Búsqueda híbrida",
        abstract="Resumen.",
        fecha=date(2024, 3, 15),
        area_path="escuela_ciencia",
        tipo="tesis",
    )
    owner_id = await make_user(session, name="Ada Lovelace")
    await make_document_author(
        session, doc_id, user_id=owner_id, status="owner", display_name="Ada Lovelace"
    )
    await session.execute(
        text("UPDATE documents SET keywords = ARRAY['bd','ir'] WHERE id = :d"),
        {"d": doc_id},
    )
    await _seed_current_version(session, doc_id)
    att_id = await _seed_attachment(session, doc_id)
    await session.commit()

    r = await client.get(f"/api/docs/{doc_id}")

    assert r.status_code == 200
    body = r.json()
    assert body["doc_id"] == doc_id
    assert body["titulo"] == "Búsqueda híbrida"
    assert body["abstract"] == "Resumen."
    assert body["fecha"] == "2024-03-15"
    assert body["area_path"] == "escuela_ciencia"
    assert body["tipo"] == "tesis"
    assert body["visibility"] == "publico"
    assert body["palabras_clave"] == ["bd", "ir"]
    assert body["manageable"] is False
    assert body["autores"] == [{"display_name": "Ada Lovelace", "user_id": owner_id}]
    assert body["archivo_principal"] == {
        "original_filename": "tesis.pdf",
        "size_bytes": 2048,
        "mime": "application/pdf",
    }
    assert body["adjuntos"] == [
        {
            "id": att_id,
            "original_filename": "datos.csv",
            "size_bytes": 512,
            "mime": "text/csv",
        }
    ]
    # Slice 1: versions field is omitted from the DTO entirely.
    assert "versions" not in body


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
async def test_get_doc_detail_denials_return_404_for_invitado(
    client, session, factory_kwargs
):
    doc_id = await make_document(session, **factory_kwargs)
    await _seed_current_version(session, doc_id)
    await session.commit()

    r = await client.get(f"/api/docs/{doc_id}")

    assert r.status_code == 404
    # Uniform envelope: no header leak, no role hint, no login nudge in the body.
    assert "x-accel-redirect" not in {k.lower() for k in r.headers}
    assert "login" not in r.text.lower()
    assert "rol" not in r.text.lower()


async def test_get_doc_detail_non_existent_returns_404(client, session):
    await session.commit()
    r = await client.get("/api/docs/999999")
    assert r.status_code == 404


async def test_get_doc_detail_pending_coauthor_on_privado_returns_404(client, session):
    """Story 10: pending coautores must not see the privado doc."""
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
    assert r.status_code == 404


@pytest.mark.parametrize(
    ("role", "visibility", "author_status"),
    [
        ("estudiante", "interno", None),
        ("docente", "interno", None),
        ("estudiante", "privado", "owner"),
        ("docente", "privado", "accepted"),
    ],
    ids=["estudiante_interno", "docente_interno", "owner_privado", "accepted_privado"],
)
async def test_get_doc_detail_positive_grants_return_200(
    client, session, role, visibility, author_status
):
    """Router→core wiring for authenticated grants. The access-predicate matrix
    itself is owned by `test_document_access_readable.py`; this test pins the
    API layer routing through `readable_where` for each grant source."""
    doc_id = await make_document(session, visibility=visibility)
    await _seed_current_version(session, doc_id)
    user_id = await make_user(session, role=role)
    if author_status is not None:
        await make_document_author(
            session,
            doc_id,
            user_id=user_id,
            status=author_status,
            display_name="Reader",
        )
    sid = await _sid_cookie(session, user_id)
    await session.commit()

    r = await client.get(f"/api/docs/{doc_id}", cookies={"sid": sid})

    assert r.status_code == 200
    assert r.json()["doc_id"] == doc_id


async def test_get_doc_detail_estudiante_on_privado_non_author_returns_404(
    client, session
):
    """Authenticated UNSAM identity alone does not unlock privado."""
    doc_id = await make_document(session, visibility="privado")
    await _seed_current_version(session, doc_id)
    other_owner = await make_user(session)
    await make_document_author(session, doc_id, user_id=other_owner, status="owner")
    requester = await make_user(session, role="estudiante")
    sid = await _sid_cookie(session, requester)
    await session.commit()

    r = await client.get(f"/api/docs/{doc_id}", cookies={"sid": sid})
    assert r.status_code == 404


async def test_download_main_file_granted_returns_x_accel_redirect(client, session):
    """Story 27 + ADR-0006 §9: granted main-file reads return 200 with
    X-Accel-Redirect, Content-Disposition from original_filename, and
    Content-Type matching the recorded MIME."""
    doc_id = await make_document(session, visibility="publico")
    await _seed_current_version(
        session,
        doc_id,
        original_filename="tesis con acentos.pdf",
        mime="application/pdf",
        sha_hex="ab" + "cd" * 31,
    )
    await session.commit()

    r = await client.get(f"/api/docs/{doc_id}/download")

    assert r.status_code == 200
    assert r.headers["x-accel-redirect"] == "/_blobs/ab/cd/" + "ab" + "cd" * 31
    assert r.headers["content-type"] == "application/pdf"
    # RFC 5987 percent-encoding for non-ASCII / spaces.
    assert r.headers["content-disposition"] == (
        "attachment; filename*=UTF-8''" + quote("tesis con acentos.pdf", safe="")
    )
    # FastAPI workers must not hold the bytes; the body is empty.
    assert r.content == b""


async def test_download_attachment_granted_returns_x_accel_redirect(client, session):
    doc_id = await make_document(session, visibility="publico")
    att_id = await _seed_attachment(
        session,
        doc_id,
        original_filename="datos.csv",
        mime="text/csv",
        sha_hex="ef" + "01" * 31,
    )
    await session.commit()

    r = await client.get(f"/api/docs/{doc_id}/attachments/{att_id}")

    assert r.status_code == 200
    assert r.headers["x-accel-redirect"] == "/_blobs/ef/01/" + "ef" + "01" * 31
    assert r.headers["content-type"] == "text/csv"
    assert r.headers["content-disposition"] == "attachment; filename*=UTF-8''datos.csv"


async def test_download_attachment_with_null_mime_falls_back_to_octet_stream(
    client, session
):
    doc_id = await make_document(session, visibility="publico")
    att_id = await _seed_attachment(
        session, doc_id, mime=None, sha_hex="12" + "34" * 31
    )
    await session.commit()

    r = await client.get(f"/api/docs/{doc_id}/attachments/{att_id}")

    assert r.status_code == 200
    assert r.headers["content-type"] == "application/octet-stream"


@pytest.mark.parametrize(
    ("role", "visibility", "author_status"),
    [
        ("estudiante", "interno", None),
        ("estudiante", "privado", "owner"),
        ("docente", "privado", "accepted"),
    ],
    ids=["estudiante_interno", "owner_privado", "accepted_privado"],
)
async def test_download_endpoints_granted_for_authenticated_roles(
    client, session, role, visibility, author_status
):
    """Both download handlers carry their own hand-rolled `readable_where`
    join; this pins their routing for authenticated grants so a future
    refactor cannot silently drop the EXISTS subquery."""
    doc_id = await make_document(session, visibility=visibility)
    await _seed_current_version(session, doc_id, sha_hex="ab" + "cd" * 31)
    att_id = await _seed_attachment(session, doc_id, sha_hex="ef" + "01" * 31)
    user_id = await make_user(session, role=role)
    if author_status is not None:
        await make_document_author(
            session,
            doc_id,
            user_id=user_id,
            status=author_status,
            display_name="Reader",
        )
    sid = await _sid_cookie(session, user_id)
    await session.commit()

    cookies = {"sid": sid}
    main = await client.get(f"/api/docs/{doc_id}/download", cookies=cookies)
    att = await client.get(f"/api/docs/{doc_id}/attachments/{att_id}", cookies=cookies)

    for r in (main, att):
        assert r.status_code == 200
        assert r.headers.get("x-accel-redirect", "").startswith("/_blobs/")


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
async def test_download_denials_return_404_with_no_x_accel_header(
    client, session, factory_kwargs
):
    """Denied downloads (stories 6, 29) must return 404 with no X-Accel-Redirect
    leak, mirroring the detail-endpoint envelope."""
    doc_id = await make_document(session, **factory_kwargs)
    await _seed_current_version(session, doc_id)
    att_id = await _seed_attachment(session, doc_id)
    await session.commit()

    main = await client.get(f"/api/docs/{doc_id}/download")
    att = await client.get(f"/api/docs/{doc_id}/attachments/{att_id}")

    for r in (main, att):
        assert r.status_code == 404
        assert "x-accel-redirect" not in {k.lower() for k in r.headers}


async def test_download_denials_pending_coauthor_on_privado(client, session):
    """Story 10: pending coautor on privado gets 404 from all three endpoints."""
    doc_id = await make_document(session, visibility="privado")
    await _seed_current_version(session, doc_id)
    att_id = await _seed_attachment(session, doc_id)
    owner_id = await make_user(session)
    pending_id = await make_user(session)
    await make_document_author(session, doc_id, user_id=owner_id, status="owner")
    await make_document_author(
        session, doc_id, user_id=pending_id, status="pending", display_name="P"
    )
    sid = await _sid_cookie(session, pending_id)
    await session.commit()

    cookies = {"sid": sid}
    detail = await client.get(f"/api/docs/{doc_id}", cookies=cookies)
    main = await client.get(f"/api/docs/{doc_id}/download", cookies=cookies)
    att = await client.get(
        f"/api/docs/{doc_id}/attachments/{att_id}", cookies=cookies
    )
    for r in (detail, main, att):
        assert r.status_code == 404
        assert "x-accel-redirect" not in {k.lower() for k in r.headers}
