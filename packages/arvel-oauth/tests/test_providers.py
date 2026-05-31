"""Provider behaviour — authorization URLs, token exchange, and identity mapping."""

from __future__ import annotations

import json
import time
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from arvel_oauth.dtos import OAuthToken
from arvel_oauth.exceptions import OAuthExchangeError
from arvel_oauth.providers import (
    AppleProvider,
    GitHubProvider,
    GoogleProvider,
)
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
)
from jwt.algorithms import ECAlgorithm

from tests.support import mock_client


def _google(handler: object = None) -> GoogleProvider:
    client = mock_client(handler) if handler is not None else None  # type: ignore[arg-type]
    return GoogleProvider(
        client_id="gid",
        client_secret="gsecret",
        redirect_uri="https://app.test/auth/google/callback",
        http_client=client,
    )


def test_google_authorization_url_includes_pkce_challenge() -> None:
    url = _google().get_authorization_url("state123", "challengeABC")
    query = parse_qs(urlparse(url).query)
    assert query["client_id"] == ["gid"]
    assert query["state"] == ["state123"]
    assert query["code_challenge"] == ["challengeABC"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["response_type"] == ["code"]


def test_google_opt_out_of_pkce_omits_challenge() -> None:
    provider = GoogleProvider(
        client_id="gid",
        client_secret="s",
        redirect_uri="https://app.test/cb",
        use_pkce=False,
    )
    url = provider.get_authorization_url("st")
    assert "code_challenge" not in parse_qs(urlparse(url).query)


async def test_google_exchange_and_get_user() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(
                200, json={"access_token": "at", "id_token": "idt", "token_type": "Bearer"}
            )
        return httpx.Response(
            200,
            json={
                "sub": "g-123",
                "email": "user@example.com",
                "email_verified": True,
                "name": "Test User",
                "picture": "https://pic",
            },
        )

    provider = _google(handler)
    token = await provider.exchange_code("code", "verifier")
    assert token.access_token == "at"
    assert token.id_token == "idt"

    user = await provider.get_user(token)
    assert user.provider == "google"
    assert user.provider_id == "g-123"
    assert user.email == "user@example.com"
    assert user.email_verified is True
    assert user.name == "Test User"


async def test_token_exchange_error_raises() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid_grant"})

    with pytest.raises(OAuthExchangeError, match="token exchange failed"):
        await _google(handler).exchange_code("bad", "v")


async def test_github_uses_emails_api_when_profile_email_private() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/user":
            return httpx.Response(
                200, json={"id": 42, "login": "octocat", "name": None, "email": None}
            )
        return httpx.Response(
            200,
            json=[
                {"email": "secondary@x.com", "primary": False, "verified": True},
                {"email": "octo@github.com", "primary": True, "verified": True},
            ],
        )

    provider = GitHubProvider(
        client_id="g",
        client_secret="s",
        redirect_uri="https://app.test/cb",
        http_client=mock_client(handler),
    )
    user = await provider.get_user(OAuthToken(access_token="at"))
    assert user.provider == "github"
    assert user.provider_id == "42"
    assert user.email == "octo@github.com"
    assert user.email_verified is True
    assert user.name == "octocat"


def test_apple_client_secret_is_signed_jwt() -> None:
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode()

    provider = AppleProvider(
        client_id="com.app.client",
        team_id="TEAM123",
        key_id="KEY123",
        private_key=pem,
        redirect_uri="https://app.test/cb",
    )
    secret = provider.client_secret_value()
    header = jwt.get_unverified_header(secret)
    assert header["kid"] == "KEY123"
    assert header["alg"] == "ES256"


def _apple_signing_keypair() -> tuple[ec.EllipticCurvePrivateKey, str, dict[str, object]]:
    """An ES256 keypair plus the public JWK Apple would publish for it."""
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode()
    jwk = json.loads(ECAlgorithm(ECAlgorithm.SHA256).to_jwk(key.public_key()))
    jwk |= {"kid": "apple-key-1", "alg": "ES256", "use": "sig"}
    return key, pem, jwk


def _apple_id_token(key: ec.EllipticCurvePrivateKey, **claims: object) -> str:
    now = int(time.time())
    payload: dict[str, object] = {
        "iss": "https://appleid.apple.com",
        "aud": "com.app.client",
        "sub": "apple-sub",
        "iat": now,
        "exp": now + 3600,
        **claims,
    }
    return jwt.encode(payload, key, algorithm="ES256", headers={"kid": "apple-key-1"})


def _apple_jwks_client(jwk: dict[str, object]) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/keys"):
            return httpx.Response(200, json={"keys": [jwk]})
        return httpx.Response(404)

    return mock_client(handler)


async def test_apple_get_user_verifies_id_token_signature() -> None:
    key, pem, jwk = _apple_signing_keypair()
    id_token = _apple_id_token(
        key,
        email="a@privaterelay.appleid.com",
        email_verified="true",
    )

    provider = AppleProvider(
        client_id="com.app.client",
        team_id="T",
        key_id="K",
        private_key=pem,
        redirect_uri="https://app.test/cb",
        http_client=_apple_jwks_client(jwk),
    )
    user = await provider.get_user(OAuthToken(access_token="at", id_token=id_token))
    assert user.provider_id == "apple-sub"
    assert user.email == "a@privaterelay.appleid.com"
    assert user.email_verified is True


async def test_apple_rejects_id_token_signed_by_wrong_key() -> None:
    _, pem, jwk = _apple_signing_keypair()
    attacker_key = ec.generate_private_key(ec.SECP256R1())
    forged = _apple_id_token(attacker_key, email="attacker@evil.test")

    provider = AppleProvider(
        client_id="com.app.client",
        team_id="T",
        key_id="K",
        private_key=pem,
        redirect_uri="https://app.test/cb",
        http_client=_apple_jwks_client(jwk),
    )
    with pytest.raises(OAuthExchangeError, match="failed verification"):
        await provider.get_user(OAuthToken(access_token="at", id_token=forged))


async def test_apple_rejects_id_token_with_unknown_kid() -> None:
    key, pem, jwk = _apple_signing_keypair()
    id_token = jwt.encode(
        {"iss": "https://appleid.apple.com", "aud": "com.app.client", "sub": "x"},
        key,
        algorithm="ES256",
        headers={"kid": "rotated-away"},
    )

    provider = AppleProvider(
        client_id="com.app.client",
        team_id="T",
        key_id="K",
        private_key=pem,
        redirect_uri="https://app.test/cb",
        http_client=_apple_jwks_client(jwk),
    )
    with pytest.raises(OAuthExchangeError, match="no key for kid"):
        await provider.get_user(OAuthToken(access_token="at", id_token=id_token))
