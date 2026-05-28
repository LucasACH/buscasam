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
            " index_status, is_current, first_published_at) "
            "VALUES (:d, 1, decode(:sha, 'hex'), :name, :b, :m, 'indexed', true, now())"
        ),
        {"d": doc_id, "sha": sha_hex, "name": original_filename, "b": bytes_, "m": mime},
    )


async def _seed_version(
    session,
    doc_id: int,
    *,
    version_no: int,
    original_filename: str,
    sha_hex: str,
    is_current: bool = False,
    bytes_: int = 1024,
    mime: str = "application/pdf",
    indexed_at: str | None = None,
    index_status: str = "indexed",
    first_published: bool = True,
) -> int:
    return (
        await session.execute(
            text(
                "INSERT INTO document_versions "
                "(doc_id, version_no, sha256, original_filename, bytes, mime, "
                " index_status, is_current, indexed_at, first_published_at) "
                "VALUES (:d, :vn, decode(:sha, 'hex'), :name, :b, :m, :st, "
                "        :cur, CAST(:idx AS timestamptz), "
                "        CASE WHEN :fp THEN now() ELSE NULL END) RETURNING id"
            ),
            {
                "d": doc_id,
                "vn": version_no,
                "sha": sha_hex,
                "name": original_filename,
                "b": bytes_,
                "m": mime,
                "cur": is_current,
                "idx": indexed_at,
                "st": index_status,
                "fp": first_published,
            },
        )
    ).scalar_one()


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


async def test_get_doc_detail_pending_coauthor_on_privado_returns_minimal(
    client, session
):
    """Slice 2 / ADR-0010 §6: a pending invitee on a privado doc gets the minimal
    disclosure block — titulo + inviter only, no abstract/archivo/adjuntos."""
    doc_id = await make_document(
        session, visibility="privado", titulo="Tesis secreta", abstract="oculto"
    )
    await _seed_current_version(session, doc_id)
    att_id = await _seed_attachment(session, doc_id)  # must NOT leak
    owner_id = await make_user(session, name="Ada Lovelace")
    pending_id = await make_user(session)
    await make_document_author(
        session, doc_id, user_id=owner_id, status="owner", display_name="Ada Lovelace"
    )
    await make_document_author(
        session, doc_id, user_id=pending_id, status="pending", display_name="P"
    )
    sid = await _sid_cookie(session, pending_id)
    await session.commit()

    r = await client.get(f"/api/docs/{doc_id}", cookies={"sid": sid})

    assert r.status_code == 200
    body = r.json()
    assert body == {
        "view": "minimal",
        "doc_id": doc_id,
        "titulo": "Tesis secreta",
        "inviter_display_name": "Ada Lovelace",
    }


@pytest.mark.parametrize(
    "visibility", ["interno", "publico"], ids=["interno", "publico"]
)
async def test_get_doc_detail_pending_invitee_on_readable_doc_returns_banner(
    client, session, visibility
):
    """Slice 2 / ADR-0010 §6: a pending invitee on a doc they can already read
    (interno as UNSAM, or publico) gets the full DetailDTO plus the invitation
    banner field — view 'detail_with_invitation'."""
    doc_id = await make_document(
        session, visibility=visibility, titulo="Abierto", abstract="visible"
    )
    await _seed_current_version(session, doc_id)
    owner_id = await make_user(session, name="Ada Lovelace")
    pending_id = await make_user(session)
    await make_document_author(
        session, doc_id, user_id=owner_id, status="owner", display_name="Ada Lovelace"
    )
    await make_document_author(
        session, doc_id, user_id=pending_id, status="pending", display_name="P"
    )
    sid = await _sid_cookie(session, pending_id)
    await session.commit()

    r = await client.get(f"/api/docs/{doc_id}", cookies={"sid": sid})

    assert r.status_code == 200
    body = r.json()
    assert body["view"] == "detail_with_invitation"
    assert body["doc_id"] == doc_id
    assert body["abstract"] == "visible"  # full detail present
    assert body["invitation"] == {"inviter_display_name": "Ada Lovelace"}


async def test_get_doc_detail_accepted_coautor_returns_plain_detail(client, session):
    """An accepted coautor reads via readable_where — view 'detail', no banner."""
    doc_id = await make_document(session, visibility="privado")
    await _seed_current_version(session, doc_id)
    owner_id = await make_user(session)
    accepted_id = await make_user(session)
    await make_document_author(session, doc_id, user_id=owner_id, status="owner")
    await make_document_author(
        session, doc_id, user_id=accepted_id, status="accepted"
    )
    sid = await _sid_cookie(session, accepted_id)
    await session.commit()

    r = await client.get(f"/api/docs/{doc_id}", cookies={"sid": sid})

    assert r.status_code == 200
    body = r.json()
    assert body["view"] == "detail"
    assert "invitation" not in body


async def test_get_doc_detail_declined_invitee_returns_404(client, session):
    """Declined is terminal — no leak of 'previously declined' (uniform 404)."""
    doc_id = await make_document(session, visibility="privado")
    await _seed_current_version(session, doc_id)
    owner_id = await make_user(session)
    declined_id = await make_user(session)
    await make_document_author(session, doc_id, user_id=owner_id, status="owner")
    await make_document_author(
        session, doc_id, user_id=declined_id, status="declined"
    )
    sid = await _sid_cookie(session, declined_id)
    await session.commit()

    r = await client.get(f"/api/docs/{doc_id}", cookies={"sid": sid})
    assert r.status_code == 404


async def test_get_doc_detail_pending_on_different_doc_returns_404(client, session):
    """A pending row on doc A grants nothing on doc B (recipient-scoped to the
    queried document)."""
    doc_a = await make_document(session, visibility="privado")
    doc_b = await make_document(session, visibility="privado")
    await _seed_current_version(session, doc_b)
    owner_id = await make_user(session)
    invitee_id = await make_user(session)
    await make_document_author(session, doc_a, user_id=invitee_id, status="pending")
    await make_document_author(session, doc_b, user_id=owner_id, status="owner")
    sid = await _sid_cookie(session, invitee_id)
    await session.commit()

    r = await client.get(f"/api/docs/{doc_b}", cookies={"sid": sid})
    assert r.status_code == 404


@pytest.mark.parametrize(
    "factory_kwargs",
    [{"soft_deleted": True}, {"moderation_hidden": True}],
    ids=["soft_deleted", "moderation_hidden"],
)
async def test_get_doc_detail_pending_on_unavailable_doc_returns_404(
    client, session, factory_kwargs
):
    """Disclosure filters soft-delete and moderation-hidden (PRD stories 32-33)."""
    doc_id = await make_document(session, visibility="privado", **factory_kwargs)
    await _seed_current_version(session, doc_id)
    owner_id = await make_user(session)
    pending_id = await make_user(session)
    await make_document_author(session, doc_id, user_id=owner_id, status="owner")
    await make_document_author(
        session, doc_id, user_id=pending_id, status="pending"
    )
    sid = await _sid_cookie(session, pending_id)
    await session.commit()

    r = await client.get(f"/api/docs/{doc_id}", cookies={"sid": sid})
    assert r.status_code == 404


async def test_get_doc_detail_guest_skips_disclosure_select(
    client, session, monkeypatch
):
    """Invitados cannot be invitees — the router must not issue the disclosure
    SELECT on the anonymous-read hot path (module map §api/docs)."""
    from buscasam.api import docs as docs_module

    called = False

    async def _spy(*args, **kwargs):
        nonlocal called
        called = True
        return None

    monkeypatch.setattr(docs_module, "get_pending_invitation", _spy)
    doc_id = await make_document(session, visibility="publico")
    await _seed_current_version(session, doc_id)
    await session.commit()

    r = await client.get(f"/api/docs/{doc_id}")  # no cookie → invitado

    assert r.status_code == 200
    assert r.json()["view"] == "detail"
    assert called is False


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


async def test_disclosure_bounded_to_detail_other_endpoints_stay_404(client, session):
    """Slice 2: the disclosure carve-out is bounded to GET /api/docs/{id}. A
    pending invitee still gets 404 from related, downloads, attachments, and
    historical-version downloads (PRD story 25 / ADR-0010 §6)."""
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
    related = await client.get(f"/api/docs/{doc_id}/related", cookies=cookies)
    main = await client.get(f"/api/docs/{doc_id}/download", cookies=cookies)
    att = await client.get(
        f"/api/docs/{doc_id}/attachments/{att_id}", cookies=cookies
    )
    version = await client.get(
        f"/api/docs/{doc_id}/versions/1/download", cookies=cookies
    )
    for r in (related, main, att, version):
        assert r.status_code == 404
        assert "x-accel-redirect" not in {k.lower() for k in r.headers}


# --- Slice 2: manager affordances (issue #44) ---


async def _seed_two_versions(session, doc_id: int) -> None:
    """A historical v1 + the published current v2 (single is_current per doc)."""
    await _seed_version(
        session,
        doc_id,
        version_no=1,
        original_filename="tesis_v1.pdf",
        sha_hex="11" * 32,
        bytes_=1000,
        indexed_at="2024-01-01T10:00:00Z",
    )
    await _seed_version(
        session,
        doc_id,
        version_no=2,
        original_filename="tesis_v2.pdf",
        sha_hex="22" * 32,
        is_current=True,
        bytes_=2000,
        indexed_at="2024-02-01T10:00:00Z",
    )


async def test_get_doc_detail_owner_sees_versions_and_manageable(client, session):
    """Owner gets the full versions array (ascending by 1-based n) and
    manageable=true. n is the row_number ordering, not version_no."""
    doc_id = await make_document(session, visibility="privado")
    owner_id = await make_user(session)
    await make_document_author(
        session, doc_id, user_id=owner_id, status="owner", display_name="Owner"
    )
    await _seed_two_versions(session, doc_id)
    sid = await _sid_cookie(session, owner_id)
    await session.commit()

    r = await client.get(f"/api/docs/{doc_id}", cookies={"sid": sid})

    assert r.status_code == 200
    body = r.json()
    assert body["manageable"] is True
    assert body["versions"] == [
        {
            "n": 1,
            "original_filename": "tesis_v1.pdf",
            "mime": "application/pdf",
            "size_bytes": 1000,
            "indexed_at": "2024-01-01T10:00:00+00:00",
            "is_current": False,
        },
        {
            "n": 2,
            "original_filename": "tesis_v2.pdf",
            "mime": "application/pdf",
            "size_bytes": 2000,
            "indexed_at": "2024-02-01T10:00:00+00:00",
            "is_current": True,
        },
    ]


async def test_get_doc_detail_accepted_coautor_sees_versions(client, session):
    """The second manageable grant source: an accepted coautor (not the owner)."""
    doc_id = await make_document(session, visibility="privado")
    owner_id = await make_user(session)
    coautor_id = await make_user(session, role="docente")
    await make_document_author(session, doc_id, user_id=owner_id, status="owner")
    await make_document_author(
        session, doc_id, user_id=coautor_id, status="accepted", display_name="Co"
    )
    await _seed_two_versions(session, doc_id)
    sid = await _sid_cookie(session, coautor_id)
    await session.commit()

    r = await client.get(f"/api/docs/{doc_id}", cookies={"sid": sid})

    assert r.status_code == 200
    body = r.json()
    assert body["manageable"] is True
    assert [v["n"] for v in body["versions"]] == [1, 2]


@pytest.mark.parametrize(
    "requester",
    ["invitado", "estudiante", "docente", "pending"],
)
async def test_get_doc_detail_non_manager_omits_versions(client, session, requester):
    """No-leak contract: any reader who is not owner/accepted gets manageable
    false and the versions key absent — even on a doc they can fully read.
    The doc carries an external-author attribution (user_id NULL), which can
    never satisfy manageable_where, so external attribution leaks nothing."""
    doc_id = await make_document(session, visibility="publico")
    owner_id = await make_user(session)
    await make_document_author(session, doc_id, user_id=owner_id, status="owner")
    await make_document_author(
        session, doc_id, status="external", display_name="Autor Externo"
    )
    await _seed_two_versions(session, doc_id)

    cookies: dict[str, str] = {}
    if requester != "invitado":
        role = "docente" if requester == "docente" else "estudiante"
        uid = await make_user(session, role=role)
        if requester == "pending":
            await make_document_author(
                session, doc_id, user_id=uid, status="pending", display_name="P"
            )
        cookies = {"sid": await _sid_cookie(session, uid)}
    await session.commit()

    r = await client.get(f"/api/docs/{doc_id}", cookies=cookies)

    assert r.status_code == 200
    body = r.json()
    assert body["manageable"] is False
    assert "versions" not in body


@pytest.mark.parametrize("author_status", ["owner", "accepted"])
async def test_version_download_manager_each_n_returns_x_accel(
    client, session, author_status
):
    """Story 26/27: owner and accepted coautor can download every historical
    version; X-Accel path + Content-Disposition come from that version's own
    row (the human original_filename, never the sha256 path)."""
    doc_id = await make_document(session, visibility="privado")
    owner_id = await make_user(session)
    await make_document_author(session, doc_id, user_id=owner_id, status="owner")
    requester_id = owner_id
    if author_status == "accepted":
        requester_id = await make_user(session, role="docente")
        await make_document_author(
            session, doc_id, user_id=requester_id, status="accepted", display_name="Co"
        )
    await _seed_two_versions(session, doc_id)
    sid = await _sid_cookie(session, requester_id)
    await session.commit()

    cookies = {"sid": sid}
    r1 = await client.get(f"/api/docs/{doc_id}/versions/1/download", cookies=cookies)
    r2 = await client.get(f"/api/docs/{doc_id}/versions/2/download", cookies=cookies)

    assert r1.status_code == 200
    assert r1.headers["x-accel-redirect"] == "/_blobs/11/11/" + "11" * 32
    assert r1.headers["content-type"] == "application/pdf"
    assert (
        r1.headers["content-disposition"]
        == "attachment; filename*=UTF-8''tesis_v1.pdf"
    )
    # FastAPI workers must not hold the bytes.
    assert r1.content == b""

    assert r2.status_code == 200
    assert r2.headers["x-accel-redirect"] == "/_blobs/22/22/" + "22" * 32
    assert (
        r2.headers["content-disposition"]
        == "attachment; filename*=UTF-8''tesis_v2.pdf"
    )


@pytest.mark.parametrize("index_status", ["pending", "processing", "indexed", "failed"])
async def test_version_download_never_published_candidate_returns_404(
    client, session, index_status
):
    """ADR-0011 §4: a candidate that was never the public current
    (first_published_at IS NULL) returns 404 with no X-Accel leak even to the
    owner, while the published current still downloads. The candidate is also
    excluded from the n-ordering, so the published row keeps n=1."""
    doc_id = await make_document(session, visibility="privado")
    owner_id = await make_user(session)
    await make_document_author(session, doc_id, user_id=owner_id, status="owner")
    await _seed_version(
        session, doc_id, version_no=1, original_filename="published.pdf",
        sha_hex="11" * 32, is_current=True,
    )
    await _seed_version(
        session, doc_id, version_no=2, original_filename="candidate.pdf",
        sha_hex="33" * 32, index_status=index_status, first_published=False,
    )
    sid = await _sid_cookie(session, owner_id)
    await session.commit()

    cookies = {"sid": sid}
    candidate = await client.get(
        f"/api/docs/{doc_id}/versions/2/download", cookies=cookies
    )
    assert candidate.status_code == 404
    assert "x-accel-redirect" not in {k.lower() for k in candidate.headers}

    published = await client.get(
        f"/api/docs/{doc_id}/versions/1/download", cookies=cookies
    )
    assert published.status_code == 200
    assert published.headers["x-accel-redirect"] == "/_blobs/11/11/" + "11" * 32


@pytest.mark.parametrize(
    "requester",
    ["invitado", "estudiante", "docente", "pending"],
)
async def test_version_download_non_manager_returns_404(client, session, requester):
    """Historical versions are author-only even on a publico doc whose main
    file these same readers CAN download — the manageable gate is independent
    of readability. 404 on every existing n, no X-Accel leak."""
    doc_id = await make_document(session, visibility="publico")
    owner_id = await make_user(session)
    await make_document_author(session, doc_id, user_id=owner_id, status="owner")
    await _seed_two_versions(session, doc_id)

    cookies: dict[str, str] = {}
    if requester != "invitado":
        role = "docente" if requester == "docente" else "estudiante"
        uid = await make_user(session, role=role)
        if requester == "pending":
            await make_document_author(
                session, doc_id, user_id=uid, status="pending", display_name="P"
            )
        cookies = {"sid": await _sid_cookie(session, uid)}
    await session.commit()

    for n in (1, 2):
        r = await client.get(
            f"/api/docs/{doc_id}/versions/{n}/download", cookies=cookies
        )
        assert r.status_code == 404
        assert "x-accel-redirect" not in {k.lower() for k in r.headers}


@pytest.mark.parametrize(
    "bad_n",
    ["0", "-1", "3", "abc"],
    ids=["zero", "negative", "out_of_range", "non_integer"],
)
async def test_version_download_owner_bad_n_returns_404(client, session, bad_n):
    """Uniform 404 (never 400/422) for n that does not resolve to a row:
    zero, negative, beyond max, and non-integer."""
    doc_id = await make_document(session, visibility="privado")
    owner_id = await make_user(session)
    await make_document_author(session, doc_id, user_id=owner_id, status="owner")
    await _seed_two_versions(session, doc_id)  # n resolves only for 1 and 2
    sid = await _sid_cookie(session, owner_id)
    await session.commit()

    r = await client.get(
        f"/api/docs/{doc_id}/versions/{bad_n}/download", cookies={"sid": sid}
    )

    assert r.status_code == 404
    assert "x-accel-redirect" not in {k.lower() for k in r.headers}
