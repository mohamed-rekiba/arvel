"""Auth (doc 15) — OAuth2 on httpx-oauth (mandated engine). Test-first (no network)."""

from __future__ import annotations

from arvel.auth.oauth import OAuthProvider


def _provider() -> OAuthProvider:
    return OAuthProvider(
        client_id="client-123",
        client_secret="shh",
        authorize_endpoint="https://example.com/authorize",
        access_token_endpoint="https://example.com/token",
        scopes=["email", "profile"],
    )


async def test_authorization_url_carries_params() -> None:
    url = await _provider().authorization_url("https://app.test/callback", state="xyz")
    assert url.startswith("https://example.com/authorize")
    assert "client_id=client-123" in url
    assert "state=xyz" in url
    assert "redirect_uri=https%3A%2F%2Fapp.test%2Fcallback" in url
    assert "scope=email" in url


async def test_scope_override_per_call() -> None:
    url = await _provider().authorization_url(
        "https://app.test/callback", state="s", scope=["admin"]
    )
    assert "scope=admin" in url
