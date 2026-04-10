"""Tests for AuthManager — named guard registry."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from starlette.responses import JSONResponse

from arvel.auth.auth_manager import AuthManager
from arvel.auth.contracts import GuardContract
from arvel.auth.guards.api_key_guard import ApiKeyGuard
from arvel.auth.guards.jwt_guard import JwtGuard
from arvel.auth.policy import AuthContext
from arvel.auth.tokens import TokenService

if TYPE_CHECKING:
    from collections.abc import MutableMapping


class FakeGuard(GuardContract):
    """Minimal guard for testing."""

    async def authenticate(self, scope: MutableMapping[str, Any]) -> AuthContext | None:
        return AuthContext(user=None, sub="fake-user", guard="fake")

    def error_response(self) -> JSONResponse:
        return JSONResponse({"error": "fake"}, status_code=401)


def _token_service() -> TokenService:
    return TokenService(secret_key="test-secret-key-that-is-long-enough")


def _make_guards() -> dict[str, GuardContract]:
    return {
        "jwt": JwtGuard(token_service=_token_service()),
        "api_key": ApiKeyGuard(api_keys=["key-123"]),
        "fake": FakeGuard(),
    }


class TestAuthManager:
    def test_guard_returns_named_guard(self) -> None:
        manager = AuthManager(guards=_make_guards(), default="jwt")

        guard = manager.guard("api_key")

        assert isinstance(guard, ApiKeyGuard)

    def test_guard_returns_default_when_no_name(self) -> None:
        manager = AuthManager(guards=_make_guards(), default="jwt")

        guard = manager.guard()

        assert isinstance(guard, JwtGuard)

    def test_guard_raises_for_unknown_name(self) -> None:
        manager = AuthManager(guards=_make_guards(), default="jwt")

        with pytest.raises(ValueError, match="unknown"):
            manager.guard("nonexistent")

    def test_guard_raises_for_unknown_default(self) -> None:
        with pytest.raises(ValueError, match="default"):
            AuthManager(guards=_make_guards(), default="nonexistent")

    def test_guard_with_explicit_name(self) -> None:
        manager = AuthManager(guards=_make_guards(), default="jwt")

        guard = manager.guard("fake")

        assert isinstance(guard, FakeGuard)

    def test_guards_are_frozen_after_construction(self) -> None:
        """FR-007: Guard configuration immutable after boot."""
        from types import MappingProxyType

        manager = AuthManager(guards=_make_guards(), default="jwt")

        assert isinstance(manager._guards, MappingProxyType)

    def test_empty_guards_raises(self) -> None:
        with pytest.raises(ValueError, match="guard"):
            AuthManager(guards={}, default="jwt")

    def test_guard_none_name_uses_default(self) -> None:
        manager = AuthManager(guards=_make_guards(), default="api_key")

        guard = manager.guard(None)

        assert isinstance(guard, ApiKeyGuard)
