import httpx

from tests.fixtures.oidc_issuer import MockOIDCIssuer


async def test_discovery_document_advertises_endpoints():
    with MockOIDCIssuer() as issuer:
        async with httpx.AsyncClient() as http:
            resp = await http.get(f"{issuer.issuer_url}/.well-known/openid-configuration")
            assert resp.status_code == 200
            doc = resp.json()

    assert doc["issuer"] == issuer.issuer_url
    assert doc["authorization_endpoint"].startswith(issuer.issuer_url)
    assert doc["token_endpoint"].startswith(issuer.issuer_url)
    assert doc["jwks_uri"].startswith(issuer.issuer_url)
    assert "RS256" in doc["id_token_signing_alg_values_supported"]


async def test_jwks_serves_signing_key():
    with MockOIDCIssuer() as issuer:
        async with httpx.AsyncClient() as http:
            doc = (await http.get(
                f"{issuer.issuer_url}/.well-known/openid-configuration"
            )).json()
            jwks = (await http.get(doc["jwks_uri"])).json()

    keys = jwks["keys"]
    assert len(keys) == 1
    key = keys[0]
    assert key["kty"] == "RSA"
    assert key["use"] == "sig"
    assert key["alg"] == "RS256"
    assert "kid" in key
    assert "n" in key and "e" in key
