"""Tracer 7: full discovery + token exchange + ID token decode via Authlib.

End-to-end coverage of the contract `core/auth` will rely on in slice 2.
"""
import httpx
from authlib.integrations.httpx_client import AsyncOAuth2Client
from joserfc import jwk, jwt

from tests.fixtures.oidc_issuer import MockOIDCIssuer


CLIENT_ID = "buscasam-test-client"
CLIENT_SECRET = "test-secret"
REDIRECT_URI = "https://buscasam.test/api/auth/google/callback"


async def test_authlib_completes_dance_with_configured_claims():
    with MockOIDCIssuer() as issuer:
        issuer.set_claims(
            sub="google-sub-42",
            email="ada@unsam.edu.ar",
            hd="unsam.edu.ar",
            email_verified=True,
            name="Ada Lovelace",
            picture="https://example.test/a.png",
        )

        async with httpx.AsyncClient() as http:
            discovery = (await http.get(
                f"{issuer.issuer_url}/.well-known/openid-configuration"
            )).json()
            jwks = (await http.get(discovery["jwks_uri"])).json()

        client = AsyncOAuth2Client(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            redirect_uri=REDIRECT_URI,
            scope="openid email profile",
        )
        try:
            authorize_url, state = client.create_authorization_url(
                discovery["authorization_endpoint"]
            )

            # The fixture's authorize endpoint mints a code without redirecting
            # (it never reaches a browser). Drive it directly.
            async with httpx.AsyncClient() as http:
                code_resp = await http.get(
                    authorize_url, follow_redirects=False
                )
            assert code_resp.status_code == 200, code_resp.text
            code = code_resp.json()["code"]

            token = await client.fetch_token(
                discovery["token_endpoint"],
                code=code,
                grant_type="authorization_code",
            )
        finally:
            await client.aclose()

        assert token["token_type"].lower() == "bearer"
        assert "access_token" in token
        assert "id_token" in token

        decoded = jwt.decode(token["id_token"], jwk.KeySet.import_key_set(jwks))

    claims = decoded.claims
    assert claims["iss"] == issuer.issuer_url
    assert claims["aud"] == CLIENT_ID
    assert claims["sub"] == "google-sub-42"
    assert claims["email"] == "ada@unsam.edu.ar"
    assert claims["hd"] == "unsam.edu.ar"
    assert claims["email_verified"] is True
    assert claims["name"] == "Ada Lovelace"


async def test_configurable_rejected_claims_round_trip():
    """Reach-into rejection paths: unverified email, wrong hd, missing hd."""
    with MockOIDCIssuer() as issuer:
        issuer.set_claims(
            sub="x",
            email="x@example.com",
            hd="example.com",
            email_verified=False,
        )

        async with httpx.AsyncClient() as http:
            discovery = (await http.get(
                f"{issuer.issuer_url}/.well-known/openid-configuration"
            )).json()
            jwks = (await http.get(discovery["jwks_uri"])).json()

        client = AsyncOAuth2Client(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            redirect_uri=REDIRECT_URI,
            scope="openid email",
        )
        try:
            url, _ = client.create_authorization_url(
                discovery["authorization_endpoint"]
            )
            async with httpx.AsyncClient() as http:
                code = (await http.get(url, follow_redirects=False)).json()["code"]
            token = await client.fetch_token(
                discovery["token_endpoint"],
                code=code,
                grant_type="authorization_code",
            )
        finally:
            await client.aclose()

        claims = jwt.decode(
            token["id_token"], jwk.KeySet.import_key_set(jwks)
        ).claims

    assert claims["hd"] == "example.com"
    assert claims["email_verified"] is False
