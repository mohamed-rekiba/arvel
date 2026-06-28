"""Auth (G1 hardening) — route-protection middleware: auth / guest / verified / Authorize.

Unit tests drive each middleware's handle() against the current_user ContextVar; the E2E drives a
real protected route through the HttpKernel + test client.
"""

from __future__ import annotations

from typing import Any

import pytest

from arvel import Application
from arvel.auth import current_user
from arvel.auth.middleware import (
    Authenticate,
    Authorize,
    EnsureEmailVerified,
    RequireGuest,
    default_aliases,
)
from arvel.http import HttpKernel
from arvel.http.exceptions import HttpException
from arvel.http.middleware import AuthenticateMiddleware
from arvel.kernel import set_application
from arvel.testing import client


async def _call_next(request: Any) -> str:
    return "OK"  # sentinel: the route was allowed through


class _User:
    def __init__(self, *, verified: bool = False, can: bool = True) -> None:
        self.id = 1
        self.email_verified_at = "2026-01-01T00:00:00Z" if verified else None
        self._can = can

    async def can(self, ability: str, *args: Any) -> bool:
        return self._can


# --- Authenticate ("auth") ----------------------------------------------------


@pytest.mark.asyncio
async def test_authenticate_blocks_guest_401() -> None:
    token = current_user.set(None)
    try:
        with pytest.raises(HttpException) as exc:
            await Authenticate().handle(object(), _call_next)
        assert exc.value.status == 401
    finally:
        current_user.reset(token)


@pytest.mark.asyncio
async def test_authenticate_allows_user() -> None:
    token = current_user.set(_User())
    try:
        assert await Authenticate().handle(object(), _call_next) == "OK"
    finally:
        current_user.reset(token)


# --- RequireGuest ("guest") ---------------------------------------------------


@pytest.mark.asyncio
async def test_guest_blocks_authenticated_403() -> None:
    token = current_user.set(_User())
    try:
        with pytest.raises(HttpException) as exc:
            await RequireGuest().handle(object(), _call_next)
        assert exc.value.status == 403
    finally:
        current_user.reset(token)


@pytest.mark.asyncio
async def test_guest_allows_guest() -> None:
    token = current_user.set(None)
    try:
        assert await RequireGuest().handle(object(), _call_next) == "OK"
    finally:
        current_user.reset(token)


# --- EnsureEmailVerified ("verified") -----------------------------------------


@pytest.mark.asyncio
async def test_verified_blocks_guest_401() -> None:
    token = current_user.set(None)
    try:
        with pytest.raises(HttpException) as exc:
            await EnsureEmailVerified().handle(object(), _call_next)
        assert exc.value.status == 401
    finally:
        current_user.reset(token)


@pytest.mark.asyncio
async def test_verified_blocks_unverified_403() -> None:
    token = current_user.set(_User(verified=False))
    try:
        with pytest.raises(HttpException) as exc:
            await EnsureEmailVerified().handle(object(), _call_next)
        assert exc.value.status == 403
    finally:
        current_user.reset(token)


@pytest.mark.asyncio
async def test_verified_allows_verified_user() -> None:
    token = current_user.set(_User(verified=True))
    try:
        assert await EnsureEmailVerified().handle(object(), _call_next) == "OK"
    finally:
        current_user.reset(token)


# --- Authorize(ability) -------------------------------------------------------


@pytest.mark.asyncio
async def test_authorize_allows_when_gate_permits() -> None:
    token = current_user.set(_User(can=True))
    try:
        guard = Authorize("posts.update")  # a middleware *class*
        assert await guard().handle(object(), _call_next) == "OK"
    finally:
        current_user.reset(token)


@pytest.mark.asyncio
async def test_authorize_denies_403() -> None:
    token = current_user.set(_User(can=False))
    try:
        with pytest.raises(HttpException) as exc:
            await Authorize("posts.update")().handle(object(), _call_next)
        assert exc.value.status == 403
    finally:
        current_user.reset(token)


@pytest.mark.asyncio
async def test_authorize_blocks_guest_401() -> None:
    token = current_user.set(None)
    try:
        with pytest.raises(HttpException) as exc:
            await Authorize("posts.update")().handle(object(), _call_next)
        assert exc.value.status == 401
    finally:
        current_user.reset(token)


def test_authorize_factory_returns_a_class() -> None:
    guard = Authorize("posts.update")
    assert isinstance(guard, type)  # a class — the kernel will instantiate it


def test_default_aliases() -> None:
    assert default_aliases() == {
        "auth": Authenticate,
        "guest": RequireGuest,
        "verified": EnsureEmailVerified,
    }


# --- E2E through the kernel ----------------------------------------------------


def test_protected_route_e2e() -> None:
    app = Application()

    def resolver(request: Any) -> _User | None:
        return _User() if request.header("authorization") else None

    app.instance("user_resolver", resolver)
    set_application(app)
    try:

        def handler(request: Any) -> dict[str, Any]:
            return {"ok": True}

        kernel = HttpKernel()
        kernel.global_middleware = [AuthenticateMiddleware]  # populates current_user
        kernel.alias(default_aliases())  # "auth" → Authenticate
        kernel.add_route(["GET"], "/secret", handler, middleware=["auth"])
        with client(kernel.build()) as http:
            assert http.get("/secret", headers={"authorization": "Bearer x"}).status_code == 200
            assert http.get("/secret").status_code == 401  # guest → blocked
    finally:
        set_application(None)


# --- security hardening (from the P1a security review) -------------------------


@pytest.mark.asyncio
async def test_verified_rejects_falsy_but_set_value() -> None:
    """A falsy-but-set email_verified_at ("", 0, False) must NOT count as verified (fail closed)."""

    class _EV:
        def __init__(self, value: Any) -> None:
            self.email_verified_at = value

    for falsy in ("", 0, False):
        token = current_user.set(_EV(falsy))
        try:
            with pytest.raises(HttpException) as exc:
                await EnsureEmailVerified().handle(object(), _call_next)
            assert exc.value.status == 403
        finally:
            current_user.reset(token)


def test_kernel_resets_current_user_per_request() -> None:
    """The kernel baselines current_user per request, so a leaked set() can't cross requests —
    even with NO AuthenticateMiddleware wired (structural fail-closed)."""

    def login_handler(request: Any) -> dict[str, Any]:
        current_user.set(_User())  # simulates AuthManager.login(): set, no reset
        return {"ok": True}

    def whoami(request: Any) -> dict[str, Any]:
        user = current_user.get()
        return {"user": user.id if user is not None else None}

    kernel = HttpKernel()  # note: no AuthenticateMiddleware
    kernel.get("/login", login_handler)
    kernel.get("/whoami", whoami)
    with client(kernel.build()) as http:
        assert http.get("/login").json() == {"ok": True}
        assert http.get("/whoami").json() == {"user": None}  # the prior request did NOT leak
    assert current_user.get() is None


def test_same_origin_redirect_guard() -> None:
    """render_exception's redirect-back must not become an open redirect."""
    from arvel.http.exceptions import _same_origin_or_root

    assert _same_origin_or_root("/dashboard", "app.test") == "/dashboard"  # relative
    assert (
        _same_origin_or_root("https://app.test/x", "app.test") == "https://app.test/x"
    )  # same host
    assert _same_origin_or_root("https://evil.test/x", "app.test") == "/"  # cross-origin
    assert _same_origin_or_root("//evil.test/x", "app.test") == "/"  # protocol-relative
    assert _same_origin_or_root("", "app.test") == "/"
