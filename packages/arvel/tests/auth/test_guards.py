"""Bearer-token auth guards: extraction, authentication, permission, role level."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from arvel.auth import guards
from arvel.auth.exceptions import AccountSuspendedError, InvalidCredentialsError
from arvel.auth.guards import (
    _extract_bearer,  # pyright: ignore[reportPrivateUsage]  # white-box: test the bearer parser directly
    make_permission_guard,
    make_role_level_guard,
    require_auth,
)
from arvel.http.exceptions import AuthorizationException, UnauthenticatedException


def _request(**headers: str) -> Any:
    return SimpleNamespace(headers=headers)


class _FakeService:
    def __init__(self, *, user: Any = None, error: Exception | None = None) -> None:
        self._user = user
        self._error = error

    async def me(self, *, access_token: str) -> Any:
        if self._error is not None:
            raise self._error
        return self._user


def _bind_service(monkeypatch: pytest.MonkeyPatch, service: _FakeService) -> None:
    monkeypatch.setattr(guards, "get_auth_service", lambda: service)


class TestExtractBearer:
    def test_returns_token_for_valid_header(self) -> None:
        assert _extract_bearer(_request(authorization="Bearer abc123")) == "abc123"

    def test_supports_capitalized_header(self) -> None:
        assert _extract_bearer(_request(Authorization="Bearer xyz")) == "xyz"

    def test_none_when_header_absent(self) -> None:
        assert _extract_bearer(_request()) is None

    def test_none_when_scheme_not_bearer(self) -> None:
        assert _extract_bearer(_request(authorization="Basic abc")) is None

    def test_none_when_token_empty(self) -> None:
        assert _extract_bearer(_request(authorization="Bearer ")) is None


class TestRequireAuth:
    async def test_missing_token_raises_unauthenticated(self) -> None:
        with pytest.raises(UnauthenticatedException):
            await require_auth(_request())

    async def test_returns_user_for_valid_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        user = SimpleNamespace(id=7)
        _bind_service(monkeypatch, _FakeService(user=user))
        assert await require_auth(_request(authorization="Bearer t")) is user

    async def test_invalid_credentials_becomes_unauthenticated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _bind_service(monkeypatch, _FakeService(error=InvalidCredentialsError()))
        with pytest.raises(UnauthenticatedException):
            await require_auth(_request(authorization="Bearer t"))

    async def test_suspended_account_becomes_authorization_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _bind_service(monkeypatch, _FakeService(error=AccountSuspendedError()))
        with pytest.raises(AuthorizationException):
            await require_auth(_request(authorization="Bearer t"))


class _FakeUser:
    def __init__(self, *, perms: set[str], level: int) -> None:
        self.id = 7
        self._perms = perms
        self._level = level

    async def has_permission_to(self, perm: str) -> bool:
        return perm in self._perms

    async def has_level(self, minimum: int) -> bool:
        return self._level >= minimum


def _user_model(user: _FakeUser | None) -> type:
    class _Query:
        async def first(self) -> Any:
            return user

    class _Model:
        id = 0

        @classmethod
        def where(cls, *_a: Any, **_k: Any) -> Any:
            return _Query()

    return _Model


class TestPermissionGuard:
    async def test_returns_user_when_permission_held(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _bind_service(monkeypatch, _FakeService(user=SimpleNamespace(id=7)))
        held = _FakeUser(perms={"products.create"}, level=3)
        guard = make_permission_guard(_user_model(held))
        result = await guard(_request(authorization="Bearer t"), "products.create")
        assert result is held

    async def test_raises_when_permission_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _bind_service(monkeypatch, _FakeService(user=SimpleNamespace(id=7)))
        guard = make_permission_guard(_user_model(_FakeUser(perms=set(), level=0)))
        with pytest.raises(AuthorizationException):
            await guard(_request(authorization="Bearer t"), "products.create")

    async def test_raises_when_user_not_found(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _bind_service(monkeypatch, _FakeService(user=SimpleNamespace(id=7)))
        guard = make_permission_guard(_user_model(None))
        with pytest.raises(AuthorizationException):
            await guard(_request(authorization="Bearer t"), "products.create")

    async def test_no_redundant_query_when_me_returns_user_model(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """me() already returns the configured model → guard must not re-query."""
        queries = {"count": 0}

        class _ModelUser:
            id = 0

            def __init__(self, perms: set[str]) -> None:
                self.id = 7
                self._perms = perms

            async def has_permission_to(self, perm: str) -> bool:
                return perm in self._perms

            @classmethod
            def where(cls, *_a: Any, **_k: Any) -> Any:
                queries["count"] += 1
                msg = "guard must not reload when me() already returns the user model"
                raise AssertionError(msg)

        me_user = _ModelUser({"products.create"})
        _bind_service(monkeypatch, _FakeService(user=me_user))
        guard = make_permission_guard(_ModelUser)
        result = await guard(_request(authorization="Bearer t"), "products.create")
        assert result is me_user
        assert queries["count"] == 0

    async def test_reloads_when_me_returns_other_type(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """me() returns a different type → fall back to a typed reload."""
        _bind_service(monkeypatch, _FakeService(user=SimpleNamespace(id=7)))
        held = _FakeUser(perms={"products.create"}, level=3)
        guard = make_permission_guard(_user_model(held))
        result = await guard(_request(authorization="Bearer t"), "products.create")
        assert result is held


class TestRoleLevelGuard:
    async def test_returns_user_when_level_met(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _bind_service(monkeypatch, _FakeService(user=SimpleNamespace(id=7)))
        user = _FakeUser(perms={"admin.access"}, level=3)
        guard = make_role_level_guard(_user_model(user))
        result = await guard(_request(authorization="Bearer t"), "admin.access", minimum=2)
        assert result is user

    async def test_raises_when_level_too_low(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _bind_service(monkeypatch, _FakeService(user=SimpleNamespace(id=7)))
        guard = make_role_level_guard(_user_model(_FakeUser(perms={"admin.access"}, level=1)))
        with pytest.raises(AuthorizationException):
            await guard(_request(authorization="Bearer t"), "admin.access", minimum=2)
