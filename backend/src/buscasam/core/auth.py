"""Auth chokepoint (ADR-0005 §3, module map §`core/auth`).

Single flat module. All `hd`→role mapping, claim validation, session lifecycle,
JIT user upsert, and `next` validation live here so the audit surface stays
concentrated.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import MappingProxyType
from typing import Literal, Mapping
from urllib.parse import urlencode

import httpx
from authlib.integrations.base_client.errors import OAuthError
from authlib.integrations.httpx_client import AsyncOAuth2Client
from fastapi import Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from joserfc import jwk, jwt
from joserfc.errors import JoseError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.api.deps import get_session
from buscasam.settings import settings

log = logging.getLogger(__name__)

STATE_COOKIE = "oauth_state"
STATE_COOKIE_MAX_AGE = 600  # 10 minutes per ADR-0005 §4
STATE_COOKIE_SALT = "oauth-state"

SID_COOKIE = "sid"
# ADR-0005 §7: Max-Age = min(30 days, hard-cap remaining). On a fresh session
# the sliding-idle cap (30 days) is the smaller of the two.
SID_COOKIE_MAX_AGE = 30 * 24 * 3600

SESSION_SLIDING_IDLE = timedelta(days=30)
SESSION_REFRESH_INTERVAL = timedelta(hours=24)

NOT_UNSAM_REDIRECT = "/login?error=not_unsam"

Role = Literal["estudiante", "docente"]

ROLE_BY_HD: Mapping[str, Role] = MappingProxyType(
    {
        "estudiantes.unsam.edu.ar": "estudiante",
        "unsam.edu.ar": "docente",
    }
)


@dataclass(frozen=True)
class UserCtx:
    user_id: int | None
    is_unsam: bool
    role: Role | None


GUEST = UserCtx(user_id=None, is_unsam=False, role=None)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _decode_sid(raw: str) -> bytes | None:
    try:
        pad = "=" * (-len(raw) % 4)
        decoded = base64.urlsafe_b64decode(raw + pad)
    except (ValueError, TypeError):
        return None
    return decoded if len(decoded) == 32 else None


async def load_session(
    session: AsyncSession, *, sid_cookie: str | None
) -> tuple[UserCtx, bytes | None]:
    """Validate `sid_cookie`, return (UserCtx, sid_to_reissue_or_None).

    Returns `(GUEST, None)` on no/invalid/expired `sid` — never raises. When
    the session is active and `last_seen_at < now() - 24h`, refreshes the row
    and returns the sid bytes so the caller can re-emit the cookie (ADR-0005 §6).

    Commits on refresh — callers sharing this `AsyncSession` must not expect
    a single transaction across this call and their own writes.
    """
    if not sid_cookie:
        return GUEST, None
    sid_bytes = _decode_sid(sid_cookie)
    if sid_bytes is None:
        return GUEST, None
    now = _utcnow()
    row = (
        await session.execute(
            text(
                "SELECT s.user_id, s.last_seen_at, s.expires_at, u.role "
                "FROM sessions s JOIN users u ON u.id = s.user_id "
                "WHERE s.sid = :sid"
            ),
            {"sid": sid_bytes},
        )
    ).first()
    if row is None:
        return GUEST, None
    if row.expires_at <= now or row.last_seen_at <= now - SESSION_SLIDING_IDLE:
        return GUEST, None
    user_ctx = UserCtx(user_id=row.user_id, is_unsam=True, role=row.role)
    if now - row.last_seen_at > SESSION_REFRESH_INTERVAL:
        await session.execute(
            text("UPDATE sessions SET last_seen_at = :now WHERE sid = :sid"),
            {"now": now, "sid": sid_bytes},
        )
        await session.commit()
        return user_ctx, sid_bytes
    return user_ctx, None


async def current_user(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> UserCtx:
    """FastAPI dep: resolve sid cookie → UserCtx. Reissues cookie on refresh.

    May commit (via `load_session`) before the route handler runs; route
    handlers sharing this session do not get a single transaction.
    """
    user_ctx, reissue = await load_session(
        session, sid_cookie=request.cookies.get(SID_COOKIE)
    )
    if reissue is not None:
        _set_sid_cookie(response, reissue)
    return user_ctx


def require_authenticated(
    user_ctx: UserCtx = Depends(current_user),
) -> UserCtx:
    """Raise 401 if `user_ctx` is a guest; pass through otherwise."""
    if user_ctx.user_id is None:
        raise HTTPException(status_code=401)
    return user_ctx


def require_docente(
    user_ctx: UserCtx = Depends(require_authenticated),
) -> UserCtx:
    """Chain `require_authenticated` then raise 403 if role != 'docente'."""
    if user_ctx.role != "docente":
        raise HTTPException(status_code=403)
    return user_ctx


async def end_session(
    session: AsyncSession, *, sid_cookie: str | None, response: Response
) -> None:
    """Delete the sessions row addressed by `sid_cookie` and clear the cookie.

    Idempotent: a missing / malformed sid still clears the cookie (the caller
    is already past `require_authenticated`, so this is defense in depth).
    """
    sid_bytes = _decode_sid(sid_cookie) if sid_cookie else None
    if sid_bytes is not None:
        await session.execute(
            text("DELETE FROM sessions WHERE sid = :sid"), {"sid": sid_bytes}
        )
        await session.commit()
    response.delete_cookie(SID_COOKIE, path="/")


def role_from_claims(claims: Mapping[str, object]) -> Role | None:
    """Return the mapped role iff the claim set is acceptable, else None.

    Rejects (returns None) when `email_verified` is not literally True, when
    `hd` is missing, or when `hd` is not in `ROLE_BY_HD`. The cookie / DB /
    redirect machinery is the caller's job; this is the pure decision.
    """
    if claims.get("email_verified") is not True:
        return None
    hd = claims.get("hd")
    if not isinstance(hd, str):
        return None
    return ROLE_BY_HD.get(hd)


async def upsert_user(
    session: AsyncSession,
    *,
    google_sub: str,
    email: str,
    hd: str,
    role: Role,
    name: str,
    picture_url: str | None,
) -> int:
    """JIT INSERT ... ON CONFLICT (google_sub) DO UPDATE per ADR-0005 §9.

    Race-safe under concurrent first-logins; refreshes `email`, `hd`, `role`,
    `name`, `picture_url`, `last_login_at` on existing rows. Returns user_id.
    """
    return (
        await session.execute(
            text(
                """
                INSERT INTO users (google_sub, email, hd, role, name, picture_url)
                VALUES (:google_sub, :email, :hd, :role, :name, :picture_url)
                ON CONFLICT (google_sub) DO UPDATE SET
                  email         = EXCLUDED.email,
                  hd            = EXCLUDED.hd,
                  role          = EXCLUDED.role,
                  name          = EXCLUDED.name,
                  picture_url   = EXCLUDED.picture_url,
                  last_login_at = now()
                RETURNING id
                """
            ),
            {
                "google_sub": google_sub,
                "email": email,
                "hd": hd,
                "role": role,
                "name": name,
                "picture_url": picture_url,
            },
        )
    ).scalar_one()


def _state_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt=STATE_COOKIE_SALT)


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    return verifier, challenge


def _redirect_uri() -> str:
    return f"{settings.base_url}/api/auth/google/callback"


async def _get_json(url: str) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as http:
        resp = await http.get(url)
        resp.raise_for_status()
        return resp.json()


def _set_state_cookie(resp: Response, value: str) -> None:
    resp.set_cookie(
        STATE_COOKIE,
        value,
        max_age=STATE_COOKIE_MAX_AGE,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )


def _reject_to_login() -> RedirectResponse:
    resp = RedirectResponse(NOT_UNSAM_REDIRECT, status_code=302)
    resp.delete_cookie(STATE_COOKIE, path="/")
    return resp


def _set_sid_cookie(resp: Response, sid: bytes) -> None:
    encoded = base64.urlsafe_b64encode(sid).rstrip(b"=").decode()
    resp.set_cookie(
        SID_COOKIE,
        encoded,
        max_age=SID_COOKIE_MAX_AGE,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )


async def begin_login(next_path: str | None) -> RedirectResponse:
    """302 to the IdP authorize endpoint with PKCE + signed state cookie.

    The `next_path` is validated (ADR-0005 §5) and carried inside the signed
    cookie so the callback can land on it without trusting the URL state alone.
    """
    safe = safe_next(next_path)
    discovery = await _get_json(settings.oidc_discovery_url)
    nonce = secrets.token_urlsafe(16)
    state = secrets.token_urlsafe(16)
    verifier, challenge = _pkce_pair()

    signed = _state_serializer().dumps(
        {
            "nonce": nonce,
            "state": state,
            "pkce_verifier": verifier,
            "next": safe,
        }
    )

    authorize_url = discovery["authorization_endpoint"] + "?" + urlencode(
        {
            "response_type": "code",
            "client_id": settings.oidc_client_id,
            "redirect_uri": _redirect_uri(),
            "scope": "openid email profile",
            "nonce": nonce,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "hd": "*",
        }
    )

    resp = RedirectResponse(authorize_url, status_code=302)
    _set_state_cookie(resp, signed)
    return resp


async def complete_login(
    *,
    code: str,
    state_param: str,
    state_cookie: str,
    session: AsyncSession,
) -> RedirectResponse:
    """Validate the OIDC callback and create the session.

    Bails to `/login?error=not_unsam` (without touching `users`/`sessions`) if
    any of: state cookie missing / unsigned / expired, state mismatch, token
    exchange fails, id_token issuer/aud/nonce/exp invalid, `email_verified`
    is not True, or `hd` is unknown.
    """
    try:
        cookie_payload = _state_serializer().loads(
            state_cookie, max_age=STATE_COOKIE_MAX_AGE
        )
    except (BadSignature, SignatureExpired):
        return _reject_to_login()
    if not secrets.compare_digest(cookie_payload["state"], state_param):
        return _reject_to_login()

    discovery = await _get_json(settings.oidc_discovery_url)
    jwks_doc = await _get_json(discovery["jwks_uri"])

    try:
        async with AsyncOAuth2Client(
            client_id=settings.oidc_client_id,
            client_secret=settings.oidc_client_secret,
            redirect_uri=_redirect_uri(),
            scope="openid email profile",
        ) as oauth:
            token = await oauth.fetch_token(
                discovery["token_endpoint"],
                code=code,
                grant_type="authorization_code",
                code_verifier=cookie_payload["pkce_verifier"],
            )
        claims = jwt.decode(
            token["id_token"], jwk.KeySet.import_key_set(jwks_doc)
        ).claims
    except (OAuthError, httpx.HTTPError, JoseError, KeyError) as e:
        log.warning("oauth callback rejected", exc_info=e)
        return _reject_to_login()

    if (
        claims.get("iss") != discovery["issuer"]
        or claims.get("aud") != settings.oidc_client_id
        or claims.get("nonce") != cookie_payload["nonce"]
        or int(claims.get("exp", 0)) <= int(time.time())
    ):
        return _reject_to_login()

    role = role_from_claims(claims)
    if role is None:
        return _reject_to_login()

    user_id = await upsert_user(
        session,
        google_sub=claims["sub"],
        email=claims["email"],
        hd=claims["hd"],
        role=role,
        name=claims.get("name", ""),
        picture_url=claims.get("picture"),
    )

    sid = secrets.token_bytes(32)
    await session.execute(
        text("INSERT INTO sessions (sid, user_id) VALUES (:sid, :uid)"),
        {"sid": sid, "uid": user_id},
    )
    await session.commit()

    resp = RedirectResponse(safe_next(cookie_payload["next"]), status_code=302)
    resp.delete_cookie(STATE_COOKIE, path="/")
    _set_sid_cookie(resp, sid)
    return resp


def safe_next(raw: str | None) -> str:
    """Return `raw` iff it is a safe in-app path; otherwise `/`.

    Guard per ADR-0005 §5: `startswith('/') and not startswith('//')`. Anything
    else (absolute URLs, protocol-relative, schemes, missing leading slash,
    empty, None) defaults to `/`.
    """
    if not raw or not raw.startswith("/") or raw.startswith("//"):
        return "/"
    return raw
