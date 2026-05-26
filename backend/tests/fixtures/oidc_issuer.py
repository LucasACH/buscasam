"""Mocked OIDC issuer Authlib can drive end-to-end in tests.

Single test seam between integration tests and the Authlib client; production
never references this module. Implements discovery, JWKS, authorize, and token
endpoints sufficient for the Google OIDC dance described in ADR-0005.
"""
from __future__ import annotations

import secrets
import socket
import threading
import time
from dataclasses import dataclass, field
from urllib.parse import parse_qs

import uvicorn
from joserfc import jwk, jwt
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route


@dataclass
class MockOIDCIssuer:
    """Run a tiny OIDC-compliant issuer on an ephemeral localhost port.

    Use as a context manager::

        with MockOIDCIssuer() as issuer:
            ...  # issuer.issuer_url is reachable

    Configure the claims returned by the token endpoint via
    ``issuer.set_claims(sub=..., email=..., hd=..., email_verified=...)``.
    """

    host: str = "127.0.0.1"
    _server: uvicorn.Server = field(init=False, default=None)
    _thread: threading.Thread = field(init=False, default=None)
    _port: int = field(init=False, default=0)
    _key: jwk.RSAKey = field(init=False, default=None)
    _claims: dict = field(init=False, default_factory=dict)
    _codes: dict[str, dict] = field(init=False, default_factory=dict)

    def __enter__(self) -> "MockOIDCIssuer":
        self._port = _pick_free_port()
        self._key = jwk.RSAKey.generate_key(
            2048, parameters={"use": "sig", "alg": "RS256"}
        )
        self._key.ensure_kid()
        app = self._build_app()
        config = uvicorn.Config(
            app,
            host=self.host,
            port=self._port,
            log_level="warning",
            lifespan="off",
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()
        _wait_for_ready(self.host, self._port)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=5)

    # --- public surface ---

    @property
    def issuer_url(self) -> str:
        return f"http://{self.host}:{self._port}"

    def set_claims(
        self,
        *,
        sub: str,
        email: str,
        hd: str,
        email_verified: bool,
        name: str | None = None,
        picture: str | None = None,
    ) -> None:
        """Configure the claims the token endpoint will emit on the next code."""
        self._claims = {
            "sub": sub,
            "email": email,
            "hd": hd,
            "email_verified": email_verified,
        }
        if name is not None:
            self._claims["name"] = name
        if picture is not None:
            self._claims["picture"] = picture

    # --- request handlers ---

    def _build_app(self) -> Starlette:
        async def discovery(_: Request) -> JSONResponse:
            base = self.issuer_url
            return JSONResponse(
                {
                    "issuer": base,
                    "authorization_endpoint": f"{base}/authorize",
                    "token_endpoint": f"{base}/token",
                    "jwks_uri": f"{base}/jwks",
                    "response_types_supported": ["code"],
                    "subject_types_supported": ["public"],
                    "id_token_signing_alg_values_supported": ["RS256"],
                }
            )

        async def jwks(_: Request) -> JSONResponse:
            pub = self._key.as_dict(private=False)
            return JSONResponse({"keys": [pub]})

        async def authorize(request: Request) -> JSONResponse:
            # Real Google would 302 back to redirect_uri with code+state.
            # The fixture returns the code inline so tests don't need a
            # callback server. Tests then post the code to /token.
            code = secrets.token_urlsafe(16)
            self._codes[code] = {
                "client_id": request.query_params.get("client_id"),
                "redirect_uri": request.query_params.get("redirect_uri"),
                "claims": dict(self._claims),
            }
            return JSONResponse(
                {"code": code, "state": request.query_params.get("state")}
            )

        async def token(request: Request) -> JSONResponse:
            body = (await request.body()).decode()
            form = {k: v[0] for k, v in parse_qs(body).items()}
            code = form.get("code")
            entry = self._codes.pop(code, None)
            if entry is None:
                return JSONResponse(
                    {"error": "invalid_grant"}, status_code=400
                )

            now = int(time.time())
            claims = {
                "iss": self.issuer_url,
                "aud": entry["client_id"],
                "iat": now,
                "exp": now + 300,
                "nonce": form.get("nonce"),
                **entry["claims"],
            }
            header = {"alg": "RS256", "kid": self._key.kid, "typ": "JWT"}
            id_token = jwt.encode(header, claims, self._key)
            return JSONResponse(
                {
                    "access_token": secrets.token_urlsafe(24),
                    "token_type": "Bearer",
                    "expires_in": 3600,
                    "id_token": id_token,
                }
            )

        return Starlette(
            routes=[
                Route("/.well-known/openid-configuration", discovery),
                Route("/jwks", jwks),
                Route("/authorize", authorize),
                Route("/token", token, methods=["POST"]),
            ]
        )


# --- helpers ---


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_ready(host: str, port: int, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.02)
    raise RuntimeError(f"OIDC fixture did not bind {host}:{port} in {timeout}s")
