"""AuthServiceProvider internals: dotted imports, provider/guard builders, validation."""

from __future__ import annotations

import pytest
from arvel.application.application import Application
from arvel.auth.config import AuthConfig, GuardConfig, JwtConfig, ProviderConfig
from arvel.auth.exceptions import AuthConfigError
from arvel.auth.guards.session import SessionGuard
from arvel.auth.provider import (
    AuthServiceProvider,
    _import_class,  # pyright: ignore[reportPrivateUsage]  # white-box: dotted-path importer
    _users_provider,  # pyright: ignore[reportPrivateUsage]  # white-box: provider lookup
)

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


def test_users_provider_returns_database_driver() -> None:
    config = _config_with_users()
    assert _users_provider(config) is config.providers["users"]


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

    def test_unknown_driver(self) -> None:
        with pytest.raises(AuthConfigError, match="Unknown auth provider driver"):
            _provider()._build_provider(  # pyright: ignore[reportPrivateUsage]  # white-box
                "users", _config_with_users(provider_driver="eloquent")
            )


class TestBuildGuard:
    def test_requires_guard_config(self) -> None:
        with pytest.raises(AuthConfigError, match="GuardConfig"):
            _provider()._build_guard(object(), _config_with_users())  # pyright: ignore[reportPrivateUsage]  # white-box

    def test_builds_session_guard(self) -> None:
        guard = _provider()._build_guard(  # pyright: ignore[reportPrivateUsage]  # white-box
            GuardConfig(driver="session", provider="users"), _config_with_users()
        )
        assert isinstance(guard, SessionGuard)
