"""Tests for OAuth2/OIDC provider contracts and utilities."""

from __future__ import annotations

from arvel.auth.oauth import (
    BUILTIN_PROVIDERS,
    OAuthProviderConfig,
    OAuthProviderRegistry,
    OAuthToken,
    OAuthUser,
    generate_oauth_state,
    generate_pkce_pair,
)


class TestPKCE:
    def test_generate_pkce_pair_returns_verifier_and_challenge(self) -> None:
        verifier, challenge = generate_pkce_pair()
        assert isinstance(verifier, str)
        assert isinstance(challenge, str)
        assert len(verifier) > 20
        assert len(challenge) > 20
        assert verifier != challenge

    def test_pkce_pairs_are_unique(self) -> None:
        pairs = [generate_pkce_pair() for _ in range(5)]
        verifiers = {v for v, _ in pairs}
        assert len(verifiers) == 5


class TestOAuthState:
    def test_generate_state_is_hex(self) -> None:
        state = generate_oauth_state()
        assert len(state) == 64  # 32 bytes hex
        int(state, 16)  # validates hex

    def test_states_are_unique(self) -> None:
        states = {generate_oauth_state() for _ in range(10)}
        assert len(states) == 10


class TestOAuthDataclasses:
    def test_oauth_token_defaults(self) -> None:
        token = OAuthToken(access_token="abc")
        assert token.token_type == "bearer"
        assert token.refresh_token is None
        assert token.expires_in is None

    def test_oauth_user_minimal(self) -> None:
        user = OAuthUser(provider="github", provider_id="123")
        assert user.email is None
        assert user.name is None
        assert user.raw == {}

    def test_oauth_user_full(self) -> None:
        user = OAuthUser(
            provider="google",
            provider_id="456",
            email="test@example.com",
            name="Test User",
            avatar_url="https://example.com/avatar.png",
            raw={"locale": "en"},
        )
        assert user.email == "test@example.com"
        assert user.raw["locale"] == "en"


class TestOAuthProviderConfig:
    def test_config_defaults(self) -> None:
        cfg = OAuthProviderConfig(
            provider_name="test",
            client_id="id",
            client_secret="secret",
            authorize_url="https://auth.test/authorize",
            token_url="https://auth.test/token",
            userinfo_url="https://auth.test/userinfo",
        )
        assert cfg.use_pkce is True
        assert "openid" in cfg.scopes
        assert cfg.redirect_uri == ""


class TestBuiltinProviders:
    def test_google_endpoints(self) -> None:
        assert "google" in BUILTIN_PROVIDERS
        google = BUILTIN_PROVIDERS["google"]
        assert "accounts.google.com" in google["authorize_url"]
        assert "googleapis.com" in google["token_url"]

    def test_github_endpoints(self) -> None:
        assert "github" in BUILTIN_PROVIDERS
        github = BUILTIN_PROVIDERS["github"]
        assert "github.com" in github["authorize_url"]

    def test_microsoft_endpoints(self) -> None:
        assert "microsoft" in BUILTIN_PROVIDERS
        ms = BUILTIN_PROVIDERS["microsoft"]
        assert "microsoftonline.com" in ms["authorize_url"]

    def test_apple_endpoints(self) -> None:
        assert "apple" in BUILTIN_PROVIDERS
        apple = BUILTIN_PROVIDERS["apple"]
        assert "appleid.apple.com" in apple["authorize_url"]


class TestProviderRegistry:
    def test_register_and_get(self) -> None:
        from unittest.mock import MagicMock

        registry = OAuthProviderRegistry()
        mock_provider = MagicMock()
        mock_provider.name = "test"
        registry.register(mock_provider)
        assert registry.get("test") is mock_provider

    def test_get_unknown_returns_none(self) -> None:
        registry = OAuthProviderRegistry()
        assert registry.get("nonexistent") is None

    def test_names_lists_registered(self) -> None:
        from unittest.mock import MagicMock

        registry = OAuthProviderRegistry()
        for name in ["google", "github"]:
            mock = MagicMock()
            mock.name = name
            registry.register(mock)
        assert set(registry.names) == {"google", "github"}

    def test_all_returns_copy(self) -> None:
        registry = OAuthProviderRegistry()
        all_providers = registry.all()
        assert isinstance(all_providers, dict)
        assert len(all_providers) == 0
