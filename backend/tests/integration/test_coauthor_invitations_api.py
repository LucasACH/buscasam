"""Integration tests for api/coauthor_invitations (issue #50, module map
§api/coauthor_invitations). Two invitee-side mutations, both require_authenticated
and Origin-checked, every miss mapped to a uniform 404. The accepted-invitee →
readable end-to-end pins the accept transition into readable_where.
"""
from __future__ import annotations

import base64
import secrets

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from buscasam.api.app import create_app
from buscasam.api.deps import get_session
from buscasam.core.jobs import coauthor_invite_event_key
from buscasam.settings import settings
from tests.factories import (
    make_document,
    make_document_author,
    make_notification,
    make_user,
)

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


async def _seed(session, *, visibility="privado", status="pending"):
    """Published doc + owner + one coautor + its invite notification + invitee
    session cookie. Returns (doc_id, invitee_user_id, notification_id, cookie)."""
    owner = await make_user(session, name="Ada")
    invitee = await make_user(session, name="Bob")
    doc_id = await make_document(session, visibility=visibility)
    await make_document_author(session, doc_id, user_id=owner, status="owner")
    await make_document_author(session, doc_id, user_id=invitee, status=status)
    nid = await make_notification(
        session,
        user_id=invitee,
        kind="coauthor_invite",
        event_key=coauthor_invite_event_key(doc_id, invitee),
    )
    cookie = await _sid_cookie(session, invitee)
    return doc_id, invitee, nid, cookie


async def _status(session, doc_id, user_id) -> str:
    return (
        await session.execute(
            text(
                "SELECT status FROM document_authors "
                "WHERE doc_id = :d AND user_id = :u"
            ),
            {"d": doc_id, "u": user_id},
        )
    ).scalar_one()


async def test_accept_returns_204_and_flips_status_and_marks_read(client, session):
    doc_id, invitee, nid, cookie = await _seed(session)

    r = await client.post(
        f"/api/coauthor_invitations/{doc_id}/accept",
        headers={"cookie": f"sid={cookie}", "origin": ORIGIN},
    )

    assert r.status_code == 204
    assert await _status(session, doc_id, invitee) == "accepted"
    read_at = (
        await session.execute(
            text("SELECT read_at FROM notifications WHERE id = :id"), {"id": nid}
        )
    ).scalar_one()
    assert read_at is not None


async def test_decline_returns_204_and_flips_status(client, session):
    doc_id, invitee, _nid, cookie = await _seed(session)

    r = await client.post(
        f"/api/coauthor_invitations/{doc_id}/decline",
        headers={"cookie": f"sid={cookie}", "origin": ORIGIN},
    )

    assert r.status_code == 204
    assert await _status(session, doc_id, invitee) == "declined"


async def test_resubmit_after_transition_returns_404(client, session):
    """Idempotent: the second accept no longer matches status='pending'."""
    doc_id, _invitee, _nid, cookie = await _seed(session)
    headers = {"cookie": f"sid={cookie}", "origin": ORIGIN}

    first = await client.post(f"/api/coauthor_invitations/{doc_id}/accept", headers=headers)
    assert first.status_code == 204
    second = await client.post(f"/api/coauthor_invitations/{doc_id}/accept", headers=headers)
    assert second.status_code == 404


async def test_accept_on_revoked_row_returns_404(client, session):
    """Owner revoked while the invitee was deciding: no pending row → 404."""
    doc_id, invitee, _nid, cookie = await _seed(session)
    await session.execute(
        text("DELETE FROM document_authors WHERE doc_id = :d AND user_id = :u"),
        {"d": doc_id, "u": invitee},
    )

    r = await client.post(
        f"/api/coauthor_invitations/{doc_id}/accept",
        headers={"cookie": f"sid={cookie}", "origin": ORIGIN},
    )
    assert r.status_code == 404


async def test_anonymous_caller_rejected(client, session):
    """No session → require_authenticated → 401, never reaching the transition."""
    doc_id, _invitee, _nid, _cookie = await _seed(session)

    accept = await client.post(f"/api/coauthor_invitations/{doc_id}/accept")
    decline = await client.post(f"/api/coauthor_invitations/{doc_id}/decline")
    assert accept.status_code == 401
    assert decline.status_code == 401


async def _seed_current_version(session, doc_id: int) -> None:
    await session.execute(
        text(
            "INSERT INTO document_versions "
            "(doc_id, version_no, sha256, original_filename, bytes, mime, "
            " index_status, is_current) "
            "VALUES (:d, 1, decode('ab', 'hex'), 'f.pdf', 1, 'application/pdf', "
            "        'indexed', true)"
        ),
        {"d": doc_id},
    )


async def test_accept_then_invitee_can_read_privado_detail(client, session):
    """End-to-end: accepting flips the invitee from the slice-2 minimal-disclosure
    view into readable_where, so the privado detail GET widens from 'minimal' to
    'detail' across the transition (AC7)."""
    doc_id, _invitee, _nid, cookie = await _seed(session, visibility="privado")
    await _seed_current_version(session, doc_id)
    headers = {"cookie": f"sid={cookie}", "origin": ORIGIN}

    before = await client.get(f"/api/docs/{doc_id}", cookies={"sid": cookie})
    assert before.status_code == 200
    assert before.json()["view"] == "minimal"

    accepted = await client.post(
        f"/api/coauthor_invitations/{doc_id}/accept", headers=headers
    )
    assert accepted.status_code == 204

    after = await client.get(f"/api/docs/{doc_id}", cookies={"sid": cookie})
    assert after.status_code == 200
    assert after.json()["view"] == "detail"
    assert after.json()["doc_id"] == doc_id


async def test_decline_keeps_invitee_out_of_readable_privado_detail(client, session):
    """A declined invitee stays denied: detail GET is 404 before and after."""
    doc_id, _invitee, _nid, cookie = await _seed(session, visibility="privado")
    await _seed_current_version(session, doc_id)
    headers = {"cookie": f"sid={cookie}", "origin": ORIGIN}

    declined = await client.post(
        f"/api/coauthor_invitations/{doc_id}/decline", headers=headers
    )
    assert declined.status_code == 204

    after = await client.get(f"/api/docs/{doc_id}", cookies={"sid": cookie})
    assert after.status_code == 404
