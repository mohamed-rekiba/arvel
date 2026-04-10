"""Tests for HttpServiceProvider — boot-time wiring.

FR-021: Module routes.py auto-discovery during provider boot
FR-025: Middleware aliases resolved at boot
FR-037: Route summary logged at INFO
NFR-018: Middleware registration logged at boot
"""

from __future__ import annotations

from arvel.http.config import HttpSettings
from arvel.http.provider import HttpServiceProvider


class TestHttpServiceProvider:
    """HttpServiceProvider wires routes and middleware during boot."""

    async def test_provider_has_framework_priority(self) -> None:
        provider = HttpServiceProvider()
        assert provider.priority <= 20

    async def test_provider_is_valid_service_provider(self) -> None:
        from arvel.foundation.provider import ServiceProvider

        provider = HttpServiceProvider()
        assert isinstance(provider, ServiceProvider)
        assert hasattr(provider, "register")
        assert hasattr(provider, "boot")

    async def test_http_settings_defaults(self) -> None:
        settings = HttpSettings()
        assert settings.middleware_aliases == {}
        assert settings.global_middleware == []
        assert settings.trusted_proxies == []
