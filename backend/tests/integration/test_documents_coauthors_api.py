"""API tests for owner-side coauthor mutations (issue #52, module map
§api/documents). POST /api/documents/{id}/coauthors invites; DELETE
.../{user_id} revokes pending rows. Owner-only; maps NotOwner→403,
CoauthorAlreadyListed→409, CoauthorNotPending→404."""
from __future__ import annotations

import base64
import secrets

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from buscasam.api.app import create_app
from buscasam.api.deps import get_session
from buscasam.core import auth
from buscasam.core.jobs import coauthor_invite_event_key
from buscasam.settings import settings
from tests.factories import (
    make_document,
    make_document_author,
    make_notification,
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


async def _seed_session(session, user_id: int) -> bytes:
    sid = secrets.token_bytes(32)
    await session.execute(
        text("INSERT INTO sessions (sid, user_id) VALUES (:sid, :uid)"),
        {"sid": sid, "uid": user_id},
    )
    return sid


def _sid(sid: bytes) -> str:
    return base64.urlsafe_b64encode(sid).rstrip(b"=").decode()


async def _seed_doc_with_owner(session, *, publication_status="draft"):
    owner = await make_user(session, name="Ada")
    doc_id = await make_document(
        session, publication_status=publication_status, titulo="t"
    )
    await make_document_author(session, doc_id, user_id=owner, status="owner")
    return doc_id, owner


async def test_get_draft_returns_is_owner_and_coauthors(client, session):
    owner = await make_user(session, name="Ada")
    doc_id = await make_document(session, publication_status="draft", titulo="t")
    await make_document_author(
        session, doc_id, user_id=owner, status="owner", display_name="Ada"
    )
    bob = await make_user(session, name="Bob")
    await make_document_author(
        session, doc_id, user_id=bob, status="pending", display_name="Bob"
    )
    await session.execute(
        text(
            "INSERT INTO document_versions "
            "(doc_id, version_no, sha256, original_filename, bytes, mime, "
            " uploaded_by, index_status, headline_fingerprint) "
            "VALUES (:d, 1, decode(repeat('00', 32), 'hex'), 'f', 1, "
            " 'application/pdf', :u, 'indexed', :fp)"
        ),
        {"d": doc_id, "u": owner, "fp": _fp("t")},
    )
    sid = await _seed_session(session, owner)
    await session.commit()

    r = await client.get(
        f"/api/documents/{doc_id}/draft",
        cookies={auth.SID_COOKIE: _sid(sid)},
    )

    assert r.status_code == 200
    body = r.json()
    assert body["is_owner"] is True
    assert [c["display_name"] for c in body["coauthors"]] == ["Ada", "Bob"]
    assert [c["status"] for c in body["coauthors"]] == ["owner", "pending"]
    assert body["coauthors"][0]["user_id"] == owner
    assert body["coauthors"][1]["user_id"] == bob


def _fp(title: str) -> str:
    from buscasam.core.chunk import headline_fingerprint
    return headline_fingerprint(title, "")


async def test_post_coauthor_on_draft_inserts_pending_204(client, session):
    doc_id, owner = await _seed_doc_with_owner(session)
    invitee = await make_user(session, name="Bob")
    sid = await _seed_session(session, owner)
    await session.commit()

    r = await client.post(
        f"/api/documents/{doc_id}/coauthors",
        json={"user_id": invitee},
        headers={"origin": settings.base_url},
        cookies={auth.SID_COOKIE: _sid(sid)},
    )

    assert r.status_code == 204
    status = (
        await session.execute(
            text(
                "SELECT status FROM document_authors "
                "WHERE doc_id = :d AND user_id = :u"
            ),
            {"d": doc_id, "u": invitee},
        )
    ).scalar_one()
    assert status == "pending"


async def test_post_coauthor_already_listed_409(client, session):
    doc_id, owner = await _seed_doc_with_owner(session)
    invitee = await make_user(session, name="Bob")
    await make_document_author(
        session, doc_id, user_id=invitee, status="declined"
    )
    sid = await _seed_session(session, owner)
    await session.commit()

    r = await client.post(
        f"/api/documents/{doc_id}/coauthors",
        json={"user_id": invitee},
        headers={"origin": settings.base_url},
        cookies={auth.SID_COOKIE: _sid(sid)},
    )
    assert r.status_code == 409


async def test_post_coauthor_non_owner_403(client, session):
    doc_id, _owner = await _seed_doc_with_owner(session)
    accepted = await make_user(session, name="Acc")
    await make_document_author(
        session, doc_id, user_id=accepted, status="accepted"
    )
    target = await make_user(session, name="Bob")
    sid = await _seed_session(session, accepted)
    await session.commit()

    r = await client.post(
        f"/api/documents/{doc_id}/coauthors",
        json={"user_id": target},
        headers={"origin": settings.base_url},
        cookies={auth.SID_COOKIE: _sid(sid)},
    )
    assert r.status_code == 403


async def test_delete_coauthor_pending_drops_row_and_notification_204(
    client, session
):
    doc_id, owner = await _seed_doc_with_owner(session, publication_status="published")
    invitee = await make_user(session, name="Bob")
    await make_document_author(session, doc_id, user_id=invitee, status="pending")
    await make_notification(
        session,
        user_id=invitee,
        kind="coauthor_invite",
        event_key=coauthor_invite_event_key(doc_id, invitee),
    )
    sid = await _seed_session(session, owner)
    await session.commit()

    r = await client.delete(
        f"/api/documents/{doc_id}/coauthors/{invitee}",
        headers={"origin": settings.base_url},
        cookies={auth.SID_COOKIE: _sid(sid)},
    )

    assert r.status_code == 204
    rows = (
        await session.execute(
            text(
                "SELECT count(*) FROM document_authors "
                "WHERE doc_id = :d AND user_id = :u"
            ),
            {"d": doc_id, "u": invitee},
        )
    ).scalar_one()
    assert rows == 0
    notifs = (
        await session.execute(
            text("SELECT count(*) FROM notifications WHERE user_id = :u"),
            {"u": invitee},
        )
    ).scalar_one()
    assert notifs == 0


async def test_delete_coauthor_accepted_404(client, session):
    doc_id, owner = await _seed_doc_with_owner(session)
    accepted = await make_user(session, name="Bob")
    await make_document_author(session, doc_id, user_id=accepted, status="accepted")
    sid = await _seed_session(session, owner)
    await session.commit()

    r = await client.delete(
        f"/api/documents/{doc_id}/coauthors/{accepted}",
        headers={"origin": settings.base_url},
        cookies={auth.SID_COOKIE: _sid(sid)},
    )
    assert r.status_code == 404


async def test_delete_coauthor_missing_404(client, session):
    doc_id, owner = await _seed_doc_with_owner(session)
    ghost = await make_user(session, name="Ghost")
    sid = await _seed_session(session, owner)
    await session.commit()

    r = await client.delete(
        f"/api/documents/{doc_id}/coauthors/{ghost}",
        headers={"origin": settings.base_url},
        cookies={auth.SID_COOKIE: _sid(sid)},
    )
    assert r.status_code == 404


async def test_delete_coauthor_non_owner_403(client, session):
    doc_id, _owner = await _seed_doc_with_owner(session)
    accepted = await make_user(session, name="Acc")
    await make_document_author(session, doc_id, user_id=accepted, status="accepted")
    invitee = await make_user(session, name="Bob")
    await make_document_author(session, doc_id, user_id=invitee, status="pending")
    sid = await _seed_session(session, accepted)
    await session.commit()

    r = await client.delete(
        f"/api/documents/{doc_id}/coauthors/{invitee}",
        headers={"origin": settings.base_url},
        cookies={auth.SID_COOKIE: _sid(sid)},
    )
    assert r.status_code == 403
