"""
guest / verified / can middleware.
Tests import from arvel.auth.middleware.* → red state.
"""

from __future__ import annotations

from typing import Any

import pytest
from arvel.auth.guard import Guard


class _FakeRequest:
    def __init__(
        self,
        user: Any = None,
        *,
        container: Any = None,
        path_params: dict[str, Any] | None = None,
    ) -> None:
        self.state = type("State", (), {"user": user})()
        self.app = type("App", (), {"state": type("State", (), {"arvel_container": container})()})()
        self.path_params = path_params or {}


async def _call_next(request: Any) -> str:
    return "next_called"


def _gate_admin_only(user: Any) -> bool:
    return bool(user.get("role") == "admin")


def _gate_allow_all(_user: Any) -> bool:
    return True


# GuestMiddleware redirects authenticated users


@pytest.mark.asyncio
async def test_guest_middleware_redirects_authenticated_user() -> None:
    from arvel.auth.middleware.guest import GuestMiddleware

    mw = GuestMiddleware(redirect_to="/dashboard")
    request = _FakeRequest(user={"id": "u1"})

    response = await mw.handle(request, _call_next)
    # Should return a redirect, not call next
    assert response != "next_called"
    assert hasattr(response, "status_code")
    assert response.status_code in (302, 303)


@pytest.mark.asyncio
async def test_guest_middleware_allows_unauthenticated_through() -> None:
    from arvel.auth.middleware.guest import GuestMiddleware

    mw = GuestMiddleware(redirect_to="/dashboard")
    request = _FakeRequest(user=None)

    result = await mw.handle(request, _call_next)
    assert result == "next_called"


# VerifiedMiddleware blocks unverified users


@pytest.mark.asyncio
async def test_verified_middleware_allows_verified_user() -> None:
    from arvel.auth.middleware.verified import VerifiedMiddleware

    class VerifiedUser:
        email_verified_at = "2026-01-01"

    mw = VerifiedMiddleware()
    request = _FakeRequest(user=VerifiedUser())

    result = await mw.handle(request, _call_next)
    assert result == "next_called"


@pytest.mark.asyncio
async def test_verified_middleware_blocks_unverified_user_with_403() -> None:
    """A logged-in but unverified user is a 403 (authorization), not a 401."""
    from arvel.auth.exceptions import AuthorizationException
    from arvel.auth.middleware.verified import VerifiedMiddleware

    class UnverifiedUser:
        email_verified_at = None

    mw = VerifiedMiddleware()
    request = _FakeRequest(user=UnverifiedUser())

    with pytest.raises(AuthorizationException) as exc_info:
        await mw.handle(request, _call_next)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_verified_middleware_rejects_unauthenticated_with_401() -> None:
    """No user at all is a 401 — log in first."""
    from arvel.auth.exceptions import UnauthenticatedException
    from arvel.auth.middleware.verified import VerifiedMiddleware

    mw = VerifiedMiddleware()
    request = _FakeRequest(user=None)

    with pytest.raises(UnauthenticatedException) as exc_info:
        await mw.handle(request, _call_next)
    assert exc_info.value.status_code == 401


# CanMiddleware enforces gate ability


@pytest.mark.asyncio
async def test_can_middleware_allows_when_gate_passes() -> None:
    from arvel.auth.gate import Gate
    from arvel.auth.middleware.can import CanMiddleware

    gate = Gate()
    gate.define("admin-only", _gate_admin_only)

    mw = CanMiddleware(gate=gate, ability="admin-only")
    request = _FakeRequest(user={"role": "admin"})

    result = await mw.handle(request, _call_next)
    assert result == "next_called"


@pytest.mark.asyncio
async def test_can_middleware_raises_when_gate_denies() -> None:
    from arvel.auth.exceptions import AuthorizationException
    from arvel.auth.gate import Gate
    from arvel.auth.middleware.can import CanMiddleware

    gate = Gate()
    gate.define("admin-only", _gate_admin_only)

    mw = CanMiddleware(gate=gate, ability="admin-only")
    request = _FakeRequest(user={"role": "user"})

    with pytest.raises(AuthorizationException):
        await mw.handle(request, _call_next)


# CanMiddleware raises Unauthenticated if no user


@pytest.mark.asyncio
async def test_can_middleware_raises_unauthenticated_when_no_user() -> None:
    from arvel.auth.exceptions import UnauthenticatedException
    from arvel.auth.gate import Gate
    from arvel.auth.middleware.can import CanMiddleware

    gate = Gate()
    gate.define("any-ability", _gate_allow_all)

    mw = CanMiddleware(gate=gate, ability="any-ability")
    request = _FakeRequest(user=None)

    with pytest.raises(UnauthenticatedException):
        await mw.handle(request, _call_next)


@pytest.mark.asyncio
async def test_can_middleware_resolves_gate_from_request_container() -> None:
    from arvel.application.application import Application
    from arvel.auth.gate import Gate
    from arvel.auth.middleware.can import CanMiddleware

    app = Application()
    app.register()
    gate = app.container.make(Gate)

    def _can_update(user: dict[str, str], post: str) -> bool:
        return user["id"] == "u1" and post == "post-1"

    gate.define("update-post", _can_update)

    mw = CanMiddleware("update-post", model_param="post")
    request = _FakeRequest(
        user={"id": "u1"},
        container=app.container,
        path_params={"post": "post-1"},
    )

    result = await mw.handle(request, _call_next)

    assert result == "next_called"


# Auth middleware attaches user to request.state.user


@pytest.mark.asyncio
async def test_auth_middleware_attaches_user_to_request_state() -> None:
    from arvel.auth.manager import AuthManager
    from arvel.auth.middleware.authenticate import OptionalAuthenticate

    class _MockGuard(Guard):
        async def user(self, request: Any) -> Any:
            return {"id": "u1"}

    manager = AuthManager(guards={"web": _MockGuard()}, default="web")
    mw = OptionalAuthenticate(manager=manager)

    class _Request:
        class state:  # noqa: N801
            user: Any = None

    request = _Request()
    await mw.handle(request, _call_next)
    assert request.state.user == {"id": "u1"}
