"""Auth (G9 hardening) — OAuth2 PKCE (RFC 7636) + userinfo. No network."""

from __future__ import annotations

import base64
import hashlib
from typing import Any
from urllib.parse import parse_qs, urlparse

from arvel.auth.oauth import OAuthProvider, fetch_userinfo, generate_pkce_pair


def _expected_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _provider(client: Any = None) -> OAuthProvider:
    return OAuthProvider(
        client_id="client-123",
        client_secret="shh",
        authorize_endpoint="https://example.com/authorize",
        access_token_endpoint="https://example.com/token",
        scopes=["email", "profile"],
        client=client,
    )


# --- PKCE pair ----------------------------------------------------------------


def test_generate_pkce_pair_is_correct_s256() -> None:
    verifier, challenge = generate_pkce_pair()
    assert 43 <= len(verifier) <= 128  # RFC 7636 length bounds
    assert "=" not in verifier and "=" not in challenge  # base64url, unpadded
    assert challenge == _expected_challenge(verifier)  # challenge = base64url(sha256(verifier))
    # fresh each call
    assert generate_pkce_pair()[0] != verifier


# --- authorize_pkce -----------------------------------------------------------


async def test_authorize_pkce_url_carries_challenge_and_binds_verifier() -> None:
    url, verifier = await _provider().authorize_pkce("https://app.test/cb", state="xyz")
    params = parse_qs(urlparse(url).query)
    assert params["code_challenge_method"] == ["S256"]
    assert params["state"] == ["xyz"]
    assert params["code_challenge"] == [_expected_challenge(verifier)]  # URL binds to the verifier


async def test_plain_authorization_url_has_no_pkce_params() -> None:
    url = await _provider().authorization_url("https://app.test/cb", state="s")
    params = parse_qs(urlparse(url).query)
    assert "code_challenge" not in params  # backward compatible — PKCE only when asked
    assert "code_challenge_method" not in params


# --- access_token forwards the verifier ---------------------------------------


class _FakeClient:
    def __init__(self) -> None:
        self.token_call: dict[str, Any] = {}

    async def get_access_token(
        self, code: str, redirect_uri: str, code_verifier: str | None = None
    ) -> dict[str, Any]:
        self.token_call = {
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
        }
        return {"access_token": "at", "id_token": "it"}


async def test_access_token_forwards_code_verifier() -> None:
    fake = _FakeClient()
    token = await _provider(fake).access_token(
        "the-code", "https://app.test/cb", code_verifier="v-123"
    )
    assert token["access_token"] == "at"
    assert fake.token_call["code_verifier"] == "v-123"  # PKCE proof sent to the token endpoint


async def test_access_token_without_pkce_sends_none() -> None:
    fake = _FakeClient()
    await _provider(fake).access_token("the-code", "https://app.test/cb")
    assert fake.token_call["code_verifier"] is None


# --- userinfo -----------------------------------------------------------------


class _FakeResponse:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._data


class _FakeHttp:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str] | None]] = []

    async def get(self, url: str, headers: dict[str, str] | None = None) -> _FakeResponse:
        self.calls.append((url, headers))
        return _FakeResponse({"sub": "abc", "email": "ada@example.com"})


async def test_fetch_userinfo_sends_bearer_and_returns_profile() -> None:
    http = _FakeHttp()
    info = await fetch_userinfo("tok-xyz", "https://idp.test/userinfo", client=http)
    assert info == {"sub": "abc", "email": "ada@example.com"}
    assert http.calls[0][0] == "https://idp.test/userinfo"
    assert http.calls[0][1] == {"Authorization": "Bearer tok-xyz"}


class _FailingHttp:
    async def get(self, url: str, headers: dict[str, str] | None = None) -> Any:
        class _Resp:
            def raise_for_status(self) -> None:
                raise RuntimeError("401 Unauthorized")

            def json(self) -> dict[str, Any]:
                raise AssertionError("must not parse a failed response")

        return _Resp()


async def test_fetch_userinfo_raises_on_non_2xx_no_partial_profile() -> None:
    import pytest

    with pytest.raises(RuntimeError, match="401"):
        await fetch_userinfo("tok", "https://idp.test/userinfo", client=_FailingHttp())
