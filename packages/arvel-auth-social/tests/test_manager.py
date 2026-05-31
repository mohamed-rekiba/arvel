"""SocialAuthManager — configured-provider resolution and error paths."""

from __future__ import annotations

import pytest
from arvel_auth_social.config import SocialAuthConfig
from arvel_auth_social.exceptions import SocialProviderNotFound
from arvel_auth_social.manager import SocialAuthManager
from arvel_auth_social.providers import GoogleProvider


def _config(**overrides: str) -> SocialAuthConfig:
    base = {
        "SOCIAL_GOOGLE_CLIENT_ID": "gid",
        "SOCIAL_GOOGLE_CLIENT_SECRET": "gsecret",
        "SOCIAL_GOOGLE_REDIRECT_URI": "https://app.test/cb",
    }
    base.update(overrides)
    return SocialAuthConfig(**base)  # type: ignore[arg-type]


def test_configured_google_provider_resolves() -> None:
    manager = SocialAuthManager(_config())
    provider = manager.provider("google")
    assert isinstance(provider, GoogleProvider)
    assert provider.client_id == "gid"
    assert "google" in manager.configured_providers()


def test_unknown_provider_raises_with_available_list() -> None:
    manager = SocialAuthManager(_config())
    with pytest.raises(SocialProviderNotFound) as exc:
        manager.provider("unknown")
    assert "unknown" in str(exc.value)
    assert "google" in str(exc.value)


def test_unconfigured_provider_not_listed() -> None:
    manager = SocialAuthManager(SocialAuthConfig())
    assert manager.configured_providers() == []
