"""AuthServiceProvider internals: dotted imports, provider/guard builders, validation."""

from __future__ import annotations

from typing import cast

import pytest
from arvel.application.application import Application
from arvel.auth.config import AuthConfig, GuardConfig, JwtConfig, ProviderConfig
from arvel.auth.exceptions import AuthConfigError
from arvel.auth.guards.session import SessionGuard
from arvel.auth.http.controller import AuthController
from arvel.auth.provider import (
    AuthServiceProvider,
    _import_class,  # pyright: ignore[reportPrivateUsage]  # white-box: dotted-path importer
    _users_provider,  # pyright: ignore[reportPrivateUsage]  # white-box: provider lookup
)
from arvel.routing import Router

_MODEL = "arvel.database.model.Model"


def _provider() -> AuthServiceProvider:
    return AuthServiceProvider(app=Application())


def _config_with_users(provider_driver: str = "database") -> AuthConfig:
    return AuthConfig(
        default="web",
        guards={"web": GuardConfig(driver="session", provider="users")},
        providers={"users": ProviderConfig(driver=provider_driver, model=_MODEL)},
    )


class TestImportClass:
    def test_rejects_path_without_module(self) -> None:
        with pytest.raises(AuthConfigError):
            _import_class("NoModuleHere")

    def test_rejects_missing_class(self) -> None:
        with pytest.raises(AuthConfigError):
            _import_class("os.DefinitelyNotARealClass")


def test_users_provider_returns_arvent_driver() -> None:
    config = _config_with_users()
    assert _users_provider(config) is config.providers["users"]


def test_provider_config_rejects_unknown_driver_at_load_time() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="not supported"):
        ProviderConfig(driver="arvent", model=_MODEL)


def test_validate_jwt_rejects_none_algorithm() -> None:
    config = AuthConfig(
        default="web",
        guards={},
        providers={},
        jwt=JwtConfig(secret="x" * 32, algorithm="none"),
    )
    with pytest.raises(AuthConfigError, match="must not be 'none'"):
        AuthServiceProvider._validate_jwt_config(config)  # pyright: ignore[reportPrivateUsage]  # white-box


class TestBuildProvider:
    def test_requires_auth_config(self) -> None:
        with pytest.raises(AuthConfigError, match="must be AuthConfig"):
            _provider()._build_provider("users", object())  # pyright: ignore[reportPrivateUsage]  # white-box

    def test_unknown_provider_name(self) -> None:
        with pytest.raises(AuthConfigError, match="not configured"):
            _provider()._build_provider("ghost", _config_with_users())  # pyright: ignore[reportPrivateUsage]  # white-box

    def test_unknown_driver_bypasses_config_validation(self) -> None:
        # _build_provider has its own guard for hand-constructed configs that
        # skip the Pydantic validator (e.g. legacy fixtures or in-memory configs).
        config = _config_with_users()
        # Mutate after construction to bypass the field_validator.
        config.providers["users"].driver = "ghost"
        with pytest.raises(AuthConfigError, match="Unknown auth provider driver"):
            _provider()._build_provider("users", config)  # pyright: ignore[reportPrivateUsage]  # white-box


class TestBuildGuard:
    def test_requires_guard_config(self) -> None:
        with pytest.raises(AuthConfigError, match="GuardConfig"):
            _provider()._build_guard(object(), _config_with_users())  # pyright: ignore[reportPrivateUsage]  # white-box

    def test_builds_session_guard(self) -> None:
        guard = _provider()._build_guard(  # pyright: ignore[reportPrivateUsage]  # white-box
            GuardConfig(driver="session", provider="users"), _config_with_users()
        )
        assert isinstance(guard, SessionGuard)


class TestMountedRoutesResolvePerRequest:
    """Handlers must resolve AuthController from the container each call, not at boot."""

    async def test_register_route_honors_rebound_controller(self) -> None:
        provider = _provider()
        container = provider.container

        seen: list[str] = []

        class _SpyController:
            def __init__(self, tag: str) -> None:
                self._tag = tag

            async def register(self, payload: object) -> str:
                _ = payload
                seen.append(self._tag)
                return self._tag

        # Bind a controller, mount, then rebind. A boot-captured handler would still
        # answer "boot"; per-request resolution must answer "rebound".
        container.instance(AuthController, cast("AuthController", _SpyController("boot")))
        provider._mount_routes(_config_with_users())  # pyright: ignore[reportPrivateUsage]  # white-box: drives route mounting
        container.instance(AuthController, cast("AuthController", _SpyController("rebound")))

        spec = next(s for s in Router.singleton().routes() if s.name == "auth.register")
        result = await spec.handler(payload=object())

        assert result == "rebound"
        assert seen == ["rebound"]
