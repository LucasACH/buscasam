"""Unit tests for `core/auth` per ADR-0005 §3 and module map §`core/auth`."""
from __future__ import annotations

import base64
import secrets
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text

from buscasam.core import auth


def _sid_cookie(sid: bytes) -> str:
    return base64.urlsafe_b64encode(sid).rstrip(b"=").decode()


@pytest_asyncio.fixture
async def user_id(session):
    return (
        await session.execute(
            text(
                "INSERT INTO users (google_sub, email, hd, role, name, picture_url) "
                "VALUES ('sub-ctx', 'ada@unsam.edu.ar', 'unsam.edu.ar', 'docente', "
                "'Ada Lovelace', 'https://example.test/a.png') RETURNING id"
            )
        )
    ).scalar_one()


def test_hd_to_role_mapping():
    assert auth.ROLE_BY_HD == {
        "estudiantes.unsam.edu.ar": "estudiante",
        "unsam.edu.ar": "docente",
        "unsam-bue.edu.ar": "docente",
    }

    with pytest.raises(KeyError):
        auth.ROLE_BY_HD["evil.com"]


@pytest.mark.parametrize(
    "raw",
    ["/buscar?q=tesis", "/", "/buscar", "/docs/42#fragment"],
)
def test_next_validation_accepts_relative_paths(raw):
    assert auth.safe_next(raw) == raw


@pytest.mark.parametrize(
    "raw",
    ["//evil.com", "https://evil.com", "buscar", "", None, "javascript:alert(1)"],
)
def test_next_validation_rejects_unsafe(raw):
    assert auth.safe_next(raw) == "/"


@pytest.mark.parametrize(
    "claims",
    [
        {"email_verified": True, "sub": "x"},  # no hd
        {"email_verified": True, "sub": "x", "hd": "example.com"},  # wrong hd
        {  # right hd but unverified email
            "email_verified": False,
            "sub": "x",
            "hd": "unsam.edu.ar",
        },
    ],
)
def test_claim_acceptance_matrix_rejects(claims, monkeypatch):
    monkeypatch.setattr(auth.settings, "env", "prod")
    assert auth.role_from_claims(claims) is None


@pytest.mark.parametrize(
    "claims",
    [
        {"email_verified": True, "sub": "x"},  # no hd
        {"email_verified": True, "sub": "x", "hd": "gmail.com"},  # non-unsam hd
    ],
)
def test_non_prod_treats_non_unsam_as_estudiante(claims, monkeypatch):
    monkeypatch.setattr(auth.settings, "env", "dev")
    assert auth.role_from_claims(claims) == "estudiante"


def test_non_prod_still_rejects_unverified_email(monkeypatch):
    monkeypatch.setattr(auth.settings, "env", "dev")
    assert (
        auth.role_from_claims({"email_verified": False, "sub": "x"}) is None
    )


def test_claim_acceptance_matrix_accepts_estudiante():
    role = auth.role_from_claims(
        {
            "email_verified": True,
            "sub": "google-sub-1",
            "hd": "estudiantes.unsam.edu.ar",
        }
    )
    assert role == "estudiante"


def test_claim_acceptance_matrix_accepts_docente():
    role = auth.role_from_claims(
        {
            "email_verified": True,
            "sub": "google-sub-2",
            "hd": "unsam.edu.ar",
        }
    )
    assert role == "docente"


async def test_jit_user_upsert(session):
    uid1 = await auth.upsert_user(
        session,
        google_sub="sub-jit",
        email="ada@unsam.edu.ar",
        hd="unsam.edu.ar",
        role="docente",
        name="Ada Lovelace",
        picture_url="https://example.test/a.png",
    )

    uid2 = await auth.upsert_user(
        session,
        google_sub="sub-jit",
        email="ada+new@unsam.edu.ar",
        hd="estudiantes.unsam.edu.ar",
        role="estudiante",
        name="Ada L.",
        picture_url=None,
    )

    assert uid1 == uid2

    count = (
        await session.execute(
            text("SELECT count(*) FROM users WHERE google_sub = 'sub-jit'")
        )
    ).scalar_one()
    assert count == 1

    row = (
        await session.execute(
            text(
                "SELECT email, hd, role, name, picture_url "
                "FROM users WHERE google_sub = 'sub-jit'"
            )
        )
    ).mappings().one()
    assert row == {
        "email": "ada+new@unsam.edu.ar",
        "hd": "estudiantes.unsam.edu.ar",
        "role": "estudiante",
        "name": "Ada L.",
        "picture_url": None,
    }


async def test_session_validity_idle_and_absolute(session, user_id, monkeypatch):
    """ADR-0005 §6: invalid when sliding-idle > 30d or absolute cap reached."""
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(auth, "_utcnow", lambda: now)

    fresh = secrets.token_bytes(32)
    idle = secrets.token_bytes(32)
    aged = secrets.token_bytes(32)

    await session.execute(
        text(
            "INSERT INTO sessions (sid, user_id, created_at, last_seen_at, expires_at) "
            "VALUES "
            "  (:fresh, :uid, :now - interval '1 day',  :now - interval '1 hour',  :now + interval '89 days'), "
            "  (:idle,  :uid, :now - interval '35 days',:now - interval '31 days', :now + interval '55 days'), "
            "  (:aged,  :uid, :now - interval '91 days',:now - interval '1 hour',  :now - interval '1 day')"
        ),
        {"fresh": fresh, "idle": idle, "aged": aged, "uid": user_id, "now": now},
    )

    fresh_ctx, fresh_reissue = await auth.load_session(
        session, sid_cookie=_sid_cookie(fresh)
    )
    idle_ctx, _ = await auth.load_session(session, sid_cookie=_sid_cookie(idle))
    aged_ctx, _ = await auth.load_session(session, sid_cookie=_sid_cookie(aged))

    assert fresh_ctx == auth.UserCtx(user_id=user_id, is_unsam=True, role="docente")
    assert fresh_reissue is None
    assert idle_ctx is auth.GUEST
    assert aged_ctx is auth.GUEST


async def test_refresh_threshold(session, user_id, monkeypatch):
    """ADR-0005 §6: signal refresh only when last_seen_at > 24h ago.

    `load_session` is read-only — the actual `UPDATE` lives in
    `current_user` and is exercised by the integration test
    `test_me_stale_session_reissues_cookie`.
    """
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(auth, "_utcnow", lambda: now)

    recent = secrets.token_bytes(32)
    stale = secrets.token_bytes(32)
    recent_last_seen = now - timedelta(hours=23)
    stale_last_seen = now - timedelta(hours=25)

    await session.execute(
        text(
            "INSERT INTO sessions (sid, user_id, created_at, last_seen_at, expires_at) "
            "VALUES "
            "  (:recent, :uid, :now - interval '2 days', :recent_seen, :now + interval '88 days'), "
            "  (:stale,  :uid, :now - interval '5 days', :stale_seen,  :now + interval '85 days')"
        ),
        {
            "recent": recent,
            "stale": stale,
            "uid": user_id,
            "now": now,
            "recent_seen": recent_last_seen,
            "stale_seen": stale_last_seen,
        },
    )

    _, recent_reissue = await auth.load_session(
        session, sid_cookie=_sid_cookie(recent)
    )
    _, stale_reissue = await auth.load_session(
        session, sid_cookie=_sid_cookie(stale)
    )

    assert recent_reissue is None
    assert stale_reissue == stale

    # No row mutation expected — load_session is pure.
    seen = dict(
        (row.sid, row.last_seen_at)
        for row in (
            await session.execute(
                text("SELECT sid, last_seen_at FROM sessions WHERE sid = ANY(:sids)"),
                {"sids": [recent, stale]},
            )
        ).all()
    )
    assert seen[recent] == recent_last_seen
    assert seen[stale] == stale_last_seen


@pytest.mark.parametrize(
    "raw",
    [None, "", "not-base64!!", "AAAA", "ZmFrZQ"],  # empty / garbage / wrong length
)
async def test_load_session_invalid_cookie_is_guest(session, raw):
    ctx, reissue = await auth.load_session(session, sid_cookie=raw)
    assert ctx is auth.GUEST
    assert reissue is None


def test_require_authenticated_rejects_guest():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        auth.require_authenticated(auth.GUEST)
    assert exc.value.status_code == 401


def test_require_authenticated_returns_user():
    uc = auth.UserCtx(user_id=7, is_unsam=True, role="estudiante")
    assert auth.require_authenticated(uc) is uc


def test_require_docente_rejects_non_docente():
    from fastapi import HTTPException

    estudiante = auth.UserCtx(user_id=7, is_unsam=True, role="estudiante")
    with pytest.raises(HTTPException) as exc:
        auth.require_docente(estudiante)
    assert exc.value.status_code == 403

    # Called directly (no `Depends` chain), `GUEST` falls through to the
    # role check and 403s. The 401-first ordering only fires when
    # `require_authenticated` is wired upstream via `Depends`; coverage for
    # that path lives in the integration tests.
    with pytest.raises(HTTPException) as exc:
        auth.require_docente(auth.GUEST)
    assert exc.value.status_code == 403


def test_require_docente_returns_docente():
    uc = auth.UserCtx(user_id=7, is_unsam=True, role="docente")
    assert auth.require_docente(uc) is uc
