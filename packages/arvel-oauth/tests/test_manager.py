"""OAuthManager — configured-provider resolution and error paths."""

from __future__ import annotations

import pytest
from arvel_oauth.config import OAuthConfig
from arvel_oauth.exceptions import ProviderNotFound
from arvel_oauth.manager import OAuthManager
from arvel_oauth.providers import GoogleProvider


def _config(**overrides: str) -> OAuthConfig:
    base = {
        "OAUTH_GOOGLE_CLIENT_ID": "gid",
        "OAUTH_GOOGLE_CLIENT_SECRET": "gsecret",
        "OAUTH_GOOGLE_REDIRECT_URI": "https://app.test/cb",
    }
    base.update(overrides)
    return OAuthConfig(**base)  # type: ignore[arg-type]


def test_configured_google_provider_resolves() -> None:
    manager = OAuthManager(_config())
    provider = manager.provider("google")
    assert isinstance(provider, GoogleProvider)
    assert provider.client_id == "gid"
    assert "google" in manager.configured_providers()


def test_unknown_provider_raises_with_available_list() -> None:
    manager = OAuthManager(_config())
    with pytest.raises(ProviderNotFound) as exc:
        manager.provider("unknown")
    assert "unknown" in str(exc.value)
    assert "google" in str(exc.value)


def test_unconfigured_provider_not_listed() -> None:
    manager = OAuthManager(OAuthConfig())
    assert manager.configured_providers() == []
