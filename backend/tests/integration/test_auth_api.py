"""Integration tests for `api/auth` per module map §`api/auth`.

The MockOIDCIssuer fixture stands in for Google; the test seam is
`BUSCASAM_OIDC_DISCOVERY_URL` (env), kept out of production code paths.
"""
from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from itsdangerous import URLSafeTimedSerializer
from sqlalchemy import text

from buscasam.api.app import create_app
from buscasam.api.deps import get_session
from buscasam.settings import settings
from tests.fixtures.oidc_issuer import MockOIDCIssuer


SECRET_KEY = "test-secret-key-for-oauth-state"
CLIENT_ID = "buscasam-test-client"
CLIENT_SECRET = "test-secret"
BASE_URL = "https://buscasam.test"


@pytest_asyncio.fixture
async def issuer(monkeypatch):
    with MockOIDCIssuer() as iss:
        monkeypatch.setattr(settings, "oidc_discovery_url", f"{iss.issuer_url}/.well-known/openid-configuration")
        monkeypatch.setattr(settings, "oidc_client_id", CLIENT_ID)
        monkeypatch.setattr(settings, "oidc_client_secret", CLIENT_SECRET)
        monkeypatch.setattr(settings, "base_url", BASE_URL)
        monkeypatch.setattr(settings, "secret_key", SECRET_KEY)
        yield iss


@pytest_asyncio.fixture
async def client(session, issuer):
    async def _session_override():
        yield session

    app = create_app()
    app.dependency_overrides[get_session] = _session_override
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


async def test_login_redirect_sets_state_cookie(client, issuer):
    r = await client.get(
        "/api/auth/login", params={"next": "/buscar"}, follow_redirects=False
    )

    assert r.status_code == 302
    location = r.headers["location"]
    assert location.startswith(f"{issuer.issuer_url}/authorize?")
    qs = parse_qs(urlparse(location).query)
    assert qs["client_id"] == [CLIENT_ID]
    assert qs["redirect_uri"] == [f"{BASE_URL}/api/auth/google/callback"]
    assert qs["response_type"] == ["code"]
    assert qs["code_challenge_method"] == ["S256"]
    assert "code_challenge" in qs
    assert "nonce" in qs
    assert "state" in qs
    assert qs["hd"] == ["*"]

    cookie_header = r.headers["set-cookie"].lower()
    assert "oauth_state=" in cookie_header
    assert "httponly" in cookie_header
    assert "secure" in cookie_header
    assert "samesite=lax" in cookie_header
    assert "max-age=600" in cookie_header
    assert "path=/" in cookie_header

    cookie_val = r.cookies["oauth_state"]
    s = URLSafeTimedSerializer(SECRET_KEY, salt="oauth-state")
    payload = s.loads(cookie_val, max_age=600)
    assert payload["next"] == "/buscar"
    assert payload["nonce"] == qs["nonce"][0]
    assert payload["state"] == qs["state"][0]
    assert "pkce_verifier" in payload


async def _drive_oauth_dance(client, issuer, *, next_path="/buscar"):
    """Replays the user-side of the flow up to the callback redirect.

    Returns (callback_response, users_count, sessions_count) so each test
    asserts its own invariants on top.
    """
    r1 = await client.get(
        "/api/auth/login", params={"next": next_path}, follow_redirects=False
    )
    assert r1.status_code == 302
    state_cookie = r1.cookies["oauth_state"]
    authorize_url = r1.headers["location"]

    async with httpx.AsyncClient() as h:
        authorize_resp = await h.get(authorize_url, follow_redirects=False)
    payload = authorize_resp.json()

    return await client.get(
        "/api/auth/google/callback",
        params={"code": payload["code"], "state": payload["state"]},
        headers={"cookie": f"oauth_state={state_cookie}"},
        follow_redirects=False,
    )


async def test_callback_happy_path(client, issuer, session):
    issuer.set_claims(
        sub="google-sub-cb",
        email="ada@unsam.edu.ar",
        hd="unsam.edu.ar",
        email_verified=True,
        name="Ada Lovelace",
        picture="https://example.test/a.png",
    )

    r = await _drive_oauth_dance(client, issuer, next_path="/buscar")

    assert r.status_code == 302
    assert r.headers["location"] == "/buscar"

    sid_cookie = r.cookies.get("sid")
    assert sid_cookie is not None
    set_cookie_lower = r.headers["set-cookie"].lower()
    assert "sid=" in set_cookie_lower
    assert "httponly" in set_cookie_lower
    assert "secure" in set_cookie_lower
    assert "samesite=lax" in set_cookie_lower
    assert "path=/" in set_cookie_lower

    users_count = (
        await session.execute(
            text("SELECT count(*) FROM users WHERE google_sub = 'google-sub-cb'")
        )
    ).scalar_one()
    sessions_count = (
        await session.execute(text("SELECT count(*) FROM sessions"))
    ).scalar_one()
    assert users_count == 1
    assert sessions_count == 1

    row = (
        await session.execute(
            text(
                "SELECT email, hd, role, name, picture_url "
                "FROM users WHERE google_sub = 'google-sub-cb'"
            )
        )
    ).mappings().one()
    assert row == {
        "email": "ada@unsam.edu.ar",
        "hd": "unsam.edu.ar",
        "role": "docente",
        "name": "Ada Lovelace",
        "picture_url": "https://example.test/a.png",
    }


@pytest.mark.parametrize(
    "claims",
    [
        # email_verified=False — same hd as a valid docente, still rejected
        {
            "sub": "google-sub-unverified",
            "email": "ada@unsam.edu.ar",
            "hd": "unsam.edu.ar",
            "email_verified": False,
        },
        # unknown hd
        {
            "sub": "google-sub-extern",
            "email": "ada@example.com",
            "hd": "example.com",
            "email_verified": True,
        },
    ],
)
async def test_callback_rejected_claims_no_db_writes(client, issuer, session, claims):
    users_before = (
        await session.execute(text("SELECT count(*) FROM users"))
    ).scalar_one()
    sessions_before = (
        await session.execute(text("SELECT count(*) FROM sessions"))
    ).scalar_one()

    issuer.set_claims(**claims)
    r = await _drive_oauth_dance(client, issuer, next_path="/buscar")

    assert r.status_code == 302
    assert r.headers["location"] == "/login?error=not_unsam"

    users_after = (
        await session.execute(text("SELECT count(*) FROM users"))
    ).scalar_one()
    sessions_after = (
        await session.execute(text("SELECT count(*) FROM sessions"))
    ).scalar_one()
    assert users_after == users_before
    assert sessions_after == sessions_before


async def _row_counts(session):
    users = (
        await session.execute(text("SELECT count(*) FROM users"))
    ).scalar_one()
    sessions_n = (
        await session.execute(text("SELECT count(*) FROM sessions"))
    ).scalar_one()
    return users, sessions_n


async def _begin_login(client, *, next_path="/buscar"):
    r = await client.get(
        "/api/auth/login", params={"next": next_path}, follow_redirects=False
    )
    assert r.status_code == 302
    return r.cookies["oauth_state"], r.headers["location"]


async def _exchange_authorize(authorize_url):
    async with httpx.AsyncClient() as h:
        authorize_resp = await h.get(authorize_url, follow_redirects=False)
    return authorize_resp.json()


async def test_callback_missing_state_cookie_no_db_writes(client, issuer, session):
    issuer.set_claims(
        sub="google-sub-nocookie",
        email="ada@unsam.edu.ar",
        hd="unsam.edu.ar",
        email_verified=True,
    )
    users_before, sessions_before = await _row_counts(session)

    _, authorize_url = await _begin_login(client)
    payload = await _exchange_authorize(authorize_url)

    r = await client.get(
        "/api/auth/google/callback",
        params={"code": payload["code"], "state": payload["state"]},
        follow_redirects=False,
    )

    assert r.status_code == 302
    assert r.headers["location"] == "/login?error=not_unsam"
    assert await _row_counts(session) == (users_before, sessions_before)


async def test_callback_tampered_state_cookie_no_db_writes(client, issuer, session):
    issuer.set_claims(
        sub="google-sub-tampered",
        email="ada@unsam.edu.ar",
        hd="unsam.edu.ar",
        email_verified=True,
    )
    users_before, sessions_before = await _row_counts(session)

    state_cookie, authorize_url = await _begin_login(client)
    payload = await _exchange_authorize(authorize_url)

    tampered = state_cookie[:-4] + ("A" * 4 if state_cookie[-4:] != "AAAA" else "B" * 4)

    r = await client.get(
        "/api/auth/google/callback",
        params={"code": payload["code"], "state": payload["state"]},
        headers={"cookie": f"oauth_state={tampered}"},
        follow_redirects=False,
    )

    assert r.status_code == 302
    assert r.headers["location"] == "/login?error=not_unsam"
    assert await _row_counts(session) == (users_before, sessions_before)


async def test_callback_state_param_mismatch_no_db_writes(client, issuer, session):
    issuer.set_claims(
        sub="google-sub-mismatch",
        email="ada@unsam.edu.ar",
        hd="unsam.edu.ar",
        email_verified=True,
    )
    users_before, sessions_before = await _row_counts(session)

    state_cookie, authorize_url = await _begin_login(client)
    payload = await _exchange_authorize(authorize_url)

    r = await client.get(
        "/api/auth/google/callback",
        params={"code": payload["code"], "state": "not-the-issued-state"},
        headers={"cookie": f"oauth_state={state_cookie}"},
        follow_redirects=False,
    )

    assert r.status_code == 302
    assert r.headers["location"] == "/login?error=not_unsam"
    assert await _row_counts(session) == (users_before, sessions_before)
