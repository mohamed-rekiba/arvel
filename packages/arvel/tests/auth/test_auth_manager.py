"""
AuthManager + Auth facade.
All tests import from arvel.auth.*, which doesn't exist yet → red state.
"""

from __future__ import annotations

from typing import Any

import pytest
from arvel.auth.guard import Guard


class _FakeGuard(Guard):
    """Minimal guard stub."""

    def __init__(self, user: Any = None) -> None:
        self._user = user

    async def user(self, request: Any) -> Any | None:
        return self._user

    async def attempt(self, credentials: dict[str, object], request: Any) -> bool:
        return False

    async def login(self, user: Any, request: Any) -> None:
        pass

    async def logout(self, request: Any) -> None:
        pass


class _FakeRequest:
    pass


# Auth facade static API


@pytest.mark.asyncio
async def test_auth_facade_user_delegates_to_default_guard() -> None:
    from arvel.auth.manager import AuthManager
    from arvel.facades.auth import Auth

    sentinel = object()
    guard = _FakeGuard(user=sentinel)
    manager = AuthManager(guards={"web": guard}, default="web")
    Auth.set_manager(manager)

    result = await Auth.user(_FakeRequest())
    assert result is sentinel


def test_auth_facade_raises_when_unbound() -> None:
    from arvel.facades.auth import Auth

    previous = type.__getattribute__(Auth, "_manager")
    type.__setattr__(Auth, "_manager", None)
    try:
        with pytest.raises(RuntimeError, match="Auth facade is not bound"):
            Auth.guard()
    finally:
        type.__setattr__(Auth, "_manager", previous)


@pytest.mark.asyncio
async def test_auth_facade_check_returns_true_when_user_present() -> None:
    from arvel.auth.manager import AuthManager
    from arvel.facades.auth import Auth

    guard = _FakeGuard(user={"id": "u1"})
    manager = AuthManager(guards={"web": guard}, default="web")
    Auth.set_manager(manager)

    assert await Auth.check(_FakeRequest()) is True


@pytest.mark.asyncio
async def test_auth_facade_check_returns_false_when_no_user() -> None:
    from arvel.auth.manager import AuthManager
    from arvel.facades.auth import Auth

    guard = _FakeGuard(user=None)
    manager = AuthManager(guards={"web": guard}, default="web")
    Auth.set_manager(manager)

    assert await Auth.check(_FakeRequest()) is False


def test_auth_facade_guard_returns_named_guard() -> None:
    from arvel.auth.manager import AuthManager
    from arvel.facades.auth import Auth

    guard = _FakeGuard()
    manager = AuthManager(guards={"api": guard}, default="api")
    Auth.set_manager(manager)

    assert Auth.guard("api") is guard


# AuthManager routing


def test_auth_manager_raises_on_unknown_guard() -> None:
    from arvel.auth.exceptions import AuthConfigError
    from arvel.auth.manager import AuthManager

    manager = AuthManager(guards={"web": _FakeGuard()}, default="web")
    with pytest.raises(AuthConfigError):
        manager.guard("nonexistent")


@pytest.mark.asyncio
async def test_auth_manager_routes_to_correct_guard() -> None:
    from arvel.auth.manager import AuthManager

    api_guard = _FakeGuard(user={"id": "api-user"})
    web_guard = _FakeGuard(user={"id": "web-user"})
    manager = AuthManager(guards={"api": api_guard, "web": web_guard}, default="web")

    user = await manager.guard("api").user(_FakeRequest())
    assert user == {"id": "api-user"}


# attempt


@pytest.mark.asyncio
async def test_auth_facade_attempt_delegates_to_default_guard() -> None:
    from arvel.auth.manager import AuthManager
    from arvel.facades.auth import Auth

    class _AttemptGuard(_FakeGuard):
        async def attempt(self, credentials: dict[str, object], request: Any) -> bool:
            return credentials.get("password") == "correct"

    guard = _AttemptGuard()
    manager = AuthManager(guards={"web": guard}, default="web")
    Auth.set_manager(manager)

    ok = await Auth.attempt({"password": "correct"}, _FakeRequest())
    assert ok is True
    fail = await Auth.attempt({"password": "wrong"}, _FakeRequest())
    assert fail is False


# login / logout


@pytest.mark.asyncio
async def test_auth_facade_login_delegates_to_default_guard() -> None:
    from arvel.auth.manager import AuthManager
    from arvel.facades.auth import Auth

    logged_in: list[Any] = []

    class _LoginGuard(_FakeGuard):
        async def login(self, user: Any, request: Any) -> None:
            logged_in.append(user)

    manager = AuthManager(guards={"web": _LoginGuard()}, default="web")
    Auth.set_manager(manager)

    await Auth.login({"id": "u1"}, _FakeRequest())
    assert logged_in == [{"id": "u1"}]


@pytest.mark.asyncio
async def test_auth_facade_logout_delegates_to_default_guard() -> None:
    from arvel.auth.manager import AuthManager
    from arvel.facades.auth import Auth

    logged_out: list[Any] = []

    class _LogoutGuard(_FakeGuard):
        async def logout(self, request: Any) -> None:
            logged_out.append(True)

    manager = AuthManager(guards={"web": _LogoutGuard()}, default="web")
    Auth.set_manager(manager)

    await Auth.logout(_FakeRequest())
    assert logged_out == [True]


# default guard config


def test_auth_manager_default_guard_is_accessible_via_guard_method() -> None:
    from arvel.auth.manager import AuthManager

    guard = _FakeGuard()
    manager = AuthManager(guards={"web": guard}, default="web")
    assert manager.guard("web") is guard


# Auth facade id() helper


@pytest.mark.asyncio
async def test_auth_facade_id_returns_user_id_attribute() -> None:
    from arvel.auth.manager import AuthManager
    from arvel.facades.auth import Auth

    class _UserWithId:
        id = "u42"

    guard = _FakeGuard(user=_UserWithId())
    manager = AuthManager(guards={"web": guard}, default="web")
    Auth.set_manager(manager)

    uid = await Auth.id(_FakeRequest())
    assert uid == "u42"


@pytest.mark.asyncio
async def test_auth_facade_id_returns_none_when_not_authenticated() -> None:
    from arvel.auth.manager import AuthManager
    from arvel.facades.auth import Auth

    guard = _FakeGuard(user=None)
    manager = AuthManager(guards={"web": guard}, default="web")
    Auth.set_manager(manager)

    assert await Auth.id(_FakeRequest()) is None


@pytest.mark.asyncio
async def test_auth_facade_id_returns_none_when_user_id_is_none() -> None:
    """A logged-in user with id=None yields None, not the string 'None'."""
    from arvel.auth.manager import AuthManager
    from arvel.facades.auth import Auth

    class _UserNoId:
        id = None

    manager = AuthManager(guards={"web": _FakeGuard(user=_UserNoId())}, default="web")
    Auth.set_manager(manager)

    assert await Auth.id(_FakeRequest()) is None
