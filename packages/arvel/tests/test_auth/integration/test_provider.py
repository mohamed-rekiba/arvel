"""AuthServiceProvider integration tests — register / boot / publish."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from arvel.application import Application
from arvel.auth.broker import AuthBroker
from arvel.auth.config import AuthConfig, JwtConfig, RoutesConfig
from arvel.auth.events import PasswordResetRequested, Registered
from arvel.auth.listeners import SendPasswordResetEmail, SendVerificationEmail
from arvel.auth.provider import AuthServiceProvider
from arvel.events.dispatcher import EventDispatcher
from arvel.support.publishing import PublishRegistry

_MINIMAL_CONFIG = AuthConfig(
    default="web",
    jwt=JwtConfig(secret="test-secret-at-least-32-chars-ok"),
)


def _make_provider(config: AuthConfig | None = None) -> tuple[Application, AuthServiceProvider]:
    app = Application()
    app.container.instance(PublishRegistry, PublishRegistry())
    if config is None:
        config = _MINIMAL_CONFIG
    app.container.instance(AuthConfig, config)
    return app, AuthServiceProvider(app)


def test_register_binds_default_broker() -> None:
    """FR-028-36 — container resolves AuthBroker to default broker instance."""
    app, provider = _make_provider()
    provider.register()

    broker = app.container.make(AuthBroker)
    assert isinstance(broker, AuthBroker)


def test_register_binds_user_overridden_broker() -> None:
    """FR-028-36 — config-supplied class wins over default."""
    config = AuthConfig(
        default="web",
        jwt=JwtConfig(secret="test-secret-at-least-32-chars-ok"),
        broker_class="arvel.auth.broker.AuthBroker",
    )
    app, provider = _make_provider(config)
    provider.register()

    broker = app.container.make(AuthBroker)
    assert isinstance(broker, AuthBroker)


def test_broker_uses_refresh_token_model_by_default() -> None:
    """FR-028-40 — the default ``AuthBroker`` persists rotation via ``RefreshToken``."""
    from arvel.auth.models.refresh_token import RefreshToken

    app, provider = _make_provider()
    provider.register()

    broker = app.container.make(AuthBroker)
    assert isinstance(broker, AuthBroker)
    assert broker.refresh_token_model is RefreshToken


def test_boot_registers_routes_when_enabled() -> None:
    """FR-028-34 — config.auth.routes.enabled=True → routes registered in Router."""
    from arvel.routing import Router

    config = AuthConfig(
        default="web",
        jwt=JwtConfig(secret="test-secret-at-least-32-chars-ok"),
        routes=RoutesConfig(enabled=True, prefix="/api/auth"),
    )
    # Snapshot router state before provider registers routes.
    before = len(Router.singleton().routes())

    _, provider = _make_provider(config)
    provider.register()

    after = len(Router.singleton().routes())
    assert after > before, "Provider should register routes when enabled=True"


def test_boot_skips_routes_when_disabled() -> None:
    """FR-028-34 — config.auth.routes.enabled=False → no routes added."""
    from arvel.routing import Router

    config = AuthConfig(
        default="web",
        jwt=JwtConfig(secret="test-secret-at-least-32-chars-ok"),
        routes=RoutesConfig(enabled=False, prefix="/api/auth"),
    )
    before = len(Router.singleton().routes())

    _, provider = _make_provider(config)
    provider.register()

    after = len(Router.singleton().routes())
    assert after == before, "Provider should NOT register routes when enabled=False"


@pytest.mark.asyncio
async def test_boot_publishes_4_tags(tmp_path: Path) -> None:
    """FR-028-42 — arvel-auth-{config,views,routes,migrations} all registered."""
    app, provider = _make_provider()
    provider.register()

    with patch.object(app, "base_path", return_value=tmp_path):
        await provider.boot()

    registry = app.container.make(PublishRegistry)
    tags = {item.tag for item in registry.all()}

    assert "arvel-auth-config" in tags
    assert "arvel-auth-views" in tags
    assert "arvel-auth-routes" in tags
    assert "arvel-auth-migrations" in tags


@pytest.mark.asyncio
async def test_default_listeners_attached(tmp_path: Path) -> None:
    """FR-028-39 — default listeners wire Registered and PasswordResetRequested to mailables."""
    app, provider = _make_provider()
    dispatcher = EventDispatcher()
    app.container.instance(EventDispatcher, dispatcher)

    provider.register()
    with patch.object(app, "base_path", return_value=tmp_path):
        await provider.boot()

    registered_listeners = dispatcher.listeners(Registered)
    reset_listeners = dispatcher.listeners(PasswordResetRequested)

    assert SendVerificationEmail in registered_listeners
    assert SendPasswordResetEmail in reset_listeners
