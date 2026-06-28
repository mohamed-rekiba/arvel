"""Phase 1 — authentication guards: LocalGuard, SessionGuard, GuardManager, recast AuthManager.attempt.

LocalGuard is tested with an injected lookup (no DB); SessionGuard over the current_user ContextVar.
"""

from __future__ import annotations

from typing import Any

import pytest

from arvel.auth import Authenticatable, AuthManager, current_user
from arvel.auth.guards import GuardManager, LocalGuard, SessionGuard
from arvel.security import Hasher


def _lookup_for(stored: dict[str, str]) -> Any:
    async def _lookup(identifier: str) -> str | None:
        return stored.get(identifier)

    return _lookup


# --- LocalGuard ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_local_guard_attempt_success() -> None:
    hashed = Hasher().make("s3cret")
    guard = LocalGuard(_lookup_for({"ada": hashed}))

    principal = await guard.attempt("ada", "s3cret")
    assert principal is not None
    assert principal.provider == "local"
    assert principal.subject == "ada"


@pytest.mark.asyncio
async def test_local_guard_attempt_wrong_password() -> None:
    guard = LocalGuard(_lookup_for({"ada": Hasher().make("s3cret")}))
    assert await guard.attempt("ada", "wrong") is None


@pytest.mark.asyncio
async def test_local_guard_attempt_unknown_identifier() -> None:
    guard = LocalGuard(_lookup_for({}))
    assert await guard.attempt("nobody", "whatever") is None


@pytest.mark.asyncio
async def test_local_guard_verify_extracts_form() -> None:
    hashed = Hasher().make("pw")
    guard = LocalGuard(_lookup_for({"ada@corp.com": hashed}))

    class _Req:
        async def form(self) -> dict[str, str]:
            return {"email": "ada@corp.com", "password": "pw"}

    principal = await guard.verify(_Req())
    assert principal is not None
    assert principal.subject == "ada@corp.com"


@pytest.mark.asyncio
async def test_local_guard_verify_missing_fields_returns_none() -> None:
    guard = LocalGuard(_lookup_for({}))

    class _Req:
        async def form(self) -> dict[str, str]:
            return {}

    assert await guard.verify(_Req()) is None


# --- SessionGuard -------------------------------------------------------------


class _User(Authenticatable):
    def __init__(self, uid: int) -> None:
        self.id = uid


@pytest.mark.asyncio
async def test_session_guard_reflects_current_user() -> None:
    token = current_user.set(_User(7))
    try:
        principal = await SessionGuard().verify()
        assert principal is not None
        assert principal.provider == "session"
        assert principal.subject == "7"
    finally:
        current_user.reset(token)


@pytest.mark.asyncio
async def test_session_guard_none_when_guest() -> None:
    token = current_user.set(None)
    try:
        assert await SessionGuard().verify() is None
    finally:
        current_user.reset(token)


# --- GuardManager -------------------------------------------------------------


def test_guard_manager_default_is_session() -> None:
    mgr = GuardManager()
    assert mgr.default_driver() == "session"
    assert isinstance(mgr.guard(), SessionGuard)


def test_guard_manager_resolves_local() -> None:
    assert isinstance(GuardManager().guard("local"), LocalGuard)


def test_guard_manager_extend() -> None:
    sentinel = object()
    mgr = GuardManager()
    mgr.extend("custom", lambda _app: sentinel)
    assert mgr.guard("custom") is sentinel


# --- AuthManager.attempt (recast through LocalGuard) ---------------------------


class _PwUser(Authenticatable):
    def __init__(self, uid: int, password_hash: str) -> None:
        self.id = uid
        self.password = password_hash

    def get_auth_password(self) -> Any:
        return self.password


@pytest.mark.asyncio
async def test_auth_manager_attempt_success() -> None:
    user = _PwUser(1, Hasher().make("hunter2"))

    async def provider(_credentials: dict[str, Any]) -> Any:
        return user

    mgr = AuthManager()
    ok = await mgr.attempt({"email": "ada", "password": "hunter2"}, provider)
    assert ok is True
    assert mgr.user() is user
    mgr.logout()


@pytest.mark.asyncio
async def test_auth_manager_attempt_wrong_password() -> None:
    user = _PwUser(1, Hasher().make("hunter2"))

    async def provider(_credentials: dict[str, Any]) -> Any:
        return user

    mgr = AuthManager()
    ok = await mgr.attempt({"email": "ada", "password": "nope"}, provider)
    assert ok is False
    assert mgr.guest()
