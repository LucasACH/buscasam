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
from buscasam.core import auth, blob_store
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


async def test_patch_draft_visibility_by_coauthor_returns_403(client, session):
    # ADR-0010 §8: an accepted coauthor may edit metadata but not change
    # visibility — that stays owner-only.
    owner = await make_user(session)
    coauthor = await make_user(session)
    doc_id, _ = await _seed_candidate(session, owner_id=owner)
    await make_document_author(
        session, doc_id, user_id=coauthor, status="accepted"
    )
    coauthor_sid = await _seed_session(session, coauthor)
    await session.commit()

    r = await client.patch(
        f"/api/documents/{doc_id}",
        json={"visibility": "interno"},
        headers={"origin": settings.base_url},
        cookies={auth.SID_COOKIE: _sid_cookie(coauthor_sid)},
    )

    assert r.status_code == 403
    visibility = (
        await session.execute(
            text("SELECT visibility FROM documents WHERE id = :id"),
            {"id": doc_id},
        )
    ).scalar_one()
    assert visibility == "publico"


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


async def test_publish_returns_204_and_publishes(client, session):
    uid = await make_user(session)
    sid = await _seed_session(session, uid)
    doc_id, version_id = await _seed_candidate(session, owner_id=uid)
    await session.commit()

    r = await client.post(
        f"/api/documents/{doc_id}/publish",
        headers={"origin": settings.base_url},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 204
    status = (
        await session.execute(
            text("SELECT publication_status FROM documents WHERE id = :id"),
            {"id": doc_id},
        )
    ).scalar_one()
    assert status == "published"


async def test_publish_then_list_returns_published_at(client, session):
    uid = await make_user(session)
    sid = await _seed_session(session, uid)
    doc_id, _ = await _seed_candidate(session, owner_id=uid)
    await session.commit()

    await client.post(
        f"/api/documents/{doc_id}/publish",
        headers={"origin": settings.base_url},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )
    r = await client.get(
        "/api/me/documents", cookies={auth.SID_COOKIE: _sid_cookie(sid)}
    )

    assert r.status_code == 200
    doc = next(d for d in r.json() if d["id"] == doc_id)
    assert doc["publication_status"] == "published"
    assert doc["published_at"] is not None


async def test_get_draft_reports_is_owner(client, session):
    owner = await make_user(session)
    coauthor = await make_user(session)
    doc_id, _ = await _seed_candidate(session, owner_id=owner)
    await make_document_author(
        session, doc_id, user_id=coauthor, status="accepted"
    )
    owner_sid = await _seed_session(session, owner)
    coauthor_sid = await _seed_session(session, coauthor)
    await session.commit()

    r_owner = await client.get(
        f"/api/documents/{doc_id}/draft",
        cookies={auth.SID_COOKIE: _sid_cookie(owner_sid)},
    )
    r_coauthor = await client.get(
        f"/api/documents/{doc_id}/draft",
        cookies={auth.SID_COOKIE: _sid_cookie(coauthor_sid)},
    )

    assert r_owner.json()["is_owner"] is True
    assert r_coauthor.json()["is_owner"] is False


async def test_get_draft_versions_lists_published_excludes_candidate(client, session):
    """ADR-0011 §4 regression: a manageable caller's draft `versions` lists
    every previously published row (by 1-based n) and omits a never-public
    candidate."""
    uid = await make_user(session)
    sid = await _seed_session(session, uid)
    doc_id, _ = await _seed_candidate(session, owner_id=uid)
    # _seed_candidate's version_no=1 row is the draft's own candidate
    # (first_published_at IS NULL). Add two previously published rows.
    await session.execute(
        text(
            "INSERT INTO document_versions "
            "(doc_id, version_no, sha256, original_filename, bytes, mime, "
            " index_status, is_current, first_published_at) VALUES "
            "(:d, 2, decode('22', 'hex'), 'published-v1.pdf', 1, 'application/pdf', "
            " 'indexed', false, now()), "
            "(:d, 3, decode('33', 'hex'), 'published-v2.pdf', 1, 'application/pdf', "
            " 'indexed', true, now())"
        ),
        {"d": doc_id},
    )
    await session.commit()

    r = await client.get(
        f"/api/documents/{doc_id}/draft",
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 200
    versions = r.json()["versions"]
    assert [(v["n"], v["original_filename"]) for v in versions] == [
        (1, "published-v1.pdf"),
        (2, "published-v2.pdf"),
    ]


async def test_publish_processing_candidate_returns_409(client, session):
    uid = await make_user(session)
    sid = await _seed_session(session, uid)
    doc_id, _ = await _seed_candidate(session, owner_id=uid, index_status="processing")
    await session.commit()

    r = await client.post(
        f"/api/documents/{doc_id}/publish",
        headers={"origin": settings.base_url},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 409


async def test_publish_cross_user_returns_404(client, session):
    owner = await make_user(session)
    other = await make_user(session)
    sid = await _seed_session(session, other)
    doc_id, _ = await _seed_candidate(session, owner_id=owner)
    await session.commit()

    r = await client.post(
        f"/api/documents/{doc_id}/publish",
        headers={"origin": settings.base_url},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 404


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


@pytest.fixture
def blob_root(tmp_path, monkeypatch):
    root = tmp_path / "blobs"
    monkeypatch.setattr(blob_store, "BLOB_ROOT", root)
    return root


async def _att_count(session, doc_id: int) -> int:
    return (
        await session.execute(
            text("SELECT count(*) FROM document_attachments WHERE doc_id = :d"),
            {"d": doc_id},
        )
    ).scalar_one()


async def test_post_attachment_returns_201(client, session, blob_root):
    uid = await make_user(session)
    sid = await _seed_session(session, uid)
    doc_id, _ = await _seed_candidate(session, owner_id=uid)
    await session.commit()

    r = await client.post(
        f"/api/documents/{doc_id}/attachments",
        files={"file": ("data.csv", b"a,b\n1,2\n", "text/csv")},
        headers={"origin": settings.base_url},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 201
    body = r.json()
    assert body["original_filename"] == "data.csv"
    assert body["size_bytes"] == len(b"a,b\n1,2\n")
    assert await _att_count(session, doc_id) == 1


async def test_post_attachment_over_20mb_returns_413(client, session, blob_root):
    uid = await make_user(session)
    sid = await _seed_session(session, uid)
    doc_id, _ = await _seed_candidate(session, owner_id=uid)
    await session.commit()

    oversized = b"x" * (20_000_000 + 1)
    r = await client.post(
        f"/api/documents/{doc_id}/attachments",
        files={"file": ("big.txt", oversized, "text/plain")},
        headers={"origin": settings.base_url},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 413
    assert await _att_count(session, doc_id) == 0
    # No blob committed: put_stream unlinks its temp on overflow.
    assert [p for p in blob_root.rglob("*") if p.is_file()] == []


async def test_post_attachment_disallowed_extension_returns_415(client, session, blob_root):
    uid = await make_user(session)
    sid = await _seed_session(session, uid)
    doc_id, _ = await _seed_candidate(session, owner_id=uid)
    await session.commit()

    r = await client.post(
        f"/api/documents/{doc_id}/attachments",
        files={"file": ("evil.exe", b"MZ\x90\x00", "application/octet-stream")},
        headers={"origin": settings.base_url},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 415
    assert await _att_count(session, doc_id) == 0


async def test_post_attachment_over_cap_returns_409(client, session, blob_root):
    uid = await make_user(session)
    sid = await _seed_session(session, uid)
    doc_id, _ = await _seed_candidate(session, owner_id=uid)
    for i in range(5):
        await session.execute(
            text(
                "INSERT INTO document_attachments "
                "(doc_id, sha256, original_filename, bytes, mime) "
                "VALUES (:d, decode(:sha, 'hex'), :fn, 1, 'text/csv')"
            ),
            {"d": doc_id, "sha": f"{i:02d}" * 32, "fn": f"f{i}.csv"},
        )
    await session.commit()

    r = await client.post(
        f"/api/documents/{doc_id}/attachments",
        files={"file": ("sixth.csv", b"a,b\n", "text/csv")},
        headers={"origin": settings.base_url},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 409
    assert r.json()["detail"]["reason"] == "attachment_cap_exceeded"
    assert await _att_count(session, doc_id) == 5


async def test_post_attachment_cross_user_returns_404(client, session, blob_root):
    owner = await make_user(session)
    other = await make_user(session)
    sid = await _seed_session(session, other)
    doc_id, _ = await _seed_candidate(session, owner_id=owner)
    await session.commit()

    r = await client.post(
        f"/api/documents/{doc_id}/attachments",
        files={"file": ("data.csv", b"a,b\n", "text/csv")},
        headers={"origin": settings.base_url},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 404
    assert await _att_count(session, doc_id) == 0


async def test_delete_attachment_removes_row_keeps_blob(client, session, blob_root):
    uid = await make_user(session)
    sid = await _seed_session(session, uid)
    doc_id, _ = await _seed_candidate(session, owner_id=uid)
    await session.commit()

    post = await client.post(
        f"/api/documents/{doc_id}/attachments",
        files={"file": ("data.csv", b"a,b\n1,2\n", "text/csv")},
        headers={"origin": settings.base_url},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )
    att_id = post.json()["id"]
    sha = (
        await session.execute(
            text("SELECT encode(sha256, 'hex') FROM document_attachments WHERE id = :i"),
            {"i": att_id},
        )
    ).scalar_one()

    r = await client.delete(
        f"/api/documents/{doc_id}/attachments/{att_id}",
        headers={"origin": settings.base_url},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 204
    assert await _att_count(session, doc_id) == 0
    assert await blob_store.exists(sha) is True


async def test_delete_attachment_cross_user_returns_404(client, session, blob_root):
    owner = await make_user(session)
    other = await make_user(session)
    owner_sid = await _seed_session(session, owner)
    other_sid = await _seed_session(session, other)
    doc_id, _ = await _seed_candidate(session, owner_id=owner)
    await session.commit()

    post = await client.post(
        f"/api/documents/{doc_id}/attachments",
        files={"file": ("data.csv", b"a,b\n", "text/csv")},
        headers={"origin": settings.base_url},
        cookies={auth.SID_COOKIE: _sid_cookie(owner_sid)},
    )
    att_id = post.json()["id"]

    r = await client.delete(
        f"/api/documents/{doc_id}/attachments/{att_id}",
        headers={"origin": settings.base_url},
        cookies={auth.SID_COOKIE: _sid_cookie(other_sid)},
    )

    assert r.status_code == 404
    assert await _att_count(session, doc_id) == 1


async def test_get_draft_includes_attachments(client, session, blob_root):
    uid = await make_user(session)
    sid = await _seed_session(session, uid)
    doc_id, _ = await _seed_candidate(session, owner_id=uid)
    await session.commit()

    await client.post(
        f"/api/documents/{doc_id}/attachments",
        files={"file": ("data.csv", b"a,b\n1,2\n", "text/csv")},
        headers={"origin": settings.base_url},
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    r = await client.get(
        f"/api/documents/{doc_id}/draft",
        cookies={auth.SID_COOKIE: _sid_cookie(sid)},
    )

    assert r.status_code == 200
    atts = r.json()["attachments"]
    assert len(atts) == 1
    assert atts[0]["original_filename"] == "data.csv"
    assert atts[0]["size_bytes"] == len(b"a,b\n1,2\n")
