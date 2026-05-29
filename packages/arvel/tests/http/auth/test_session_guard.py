"""FR-002-018 — SessionGuard (updated for ADR-031: now reads request.state.session)."""

from __future__ import annotations

from typing import Any

import pytest


class _FakeSession:
    """Minimal Arvel SessionData stub."""

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self._data: dict[str, Any] = data or {}
        self.regenerated = False

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def put(self, key: str, value: Any) -> None:
        self._data[key] = value

    def forget(self, key: str) -> None:
        self._data.pop(key, None)

    def regenerate(self) -> None:
        self.regenerated = True


class _FakeResolver:
    def __init__(self, users: dict[str, dict[str, Any]]) -> None:
        self._users = users

    async def by_id(self, user_id: str) -> Any | None:
        return self._users.get(user_id)

    async def by_credentials(self, credentials: dict[str, object]) -> Any | None:
        return None


class _FakeRequest:
    def __init__(self, session: _FakeSession | None = None) -> None:
        self.state = type("State", (), {"session": session or _FakeSession()})()


@pytest.mark.asyncio
async def test_session_guard_returns_user_when_session_has_id() -> None:
    from arvel.http.auth import SessionGuard

    resolver = _FakeResolver({"u-1": {"id": "u-1", "email": "x@example.com"}})
    guard = SessionGuard(resolver=resolver, session_key="_auth_id")

    request = _FakeRequest(session=_FakeSession({"_auth_id": "u-1"}))
    user = await guard.user(request)
    assert user == {"id": "u-1", "email": "x@example.com"}


@pytest.mark.asyncio
async def test_session_guard_returns_none_when_session_missing_key() -> None:
    from arvel.http.auth import SessionGuard

    resolver = _FakeResolver({"u-1": {"id": "u-1"}})
    guard = SessionGuard(resolver=resolver)
    request = _FakeRequest(session=_FakeSession({}))

    user = await guard.user(request)
    assert user is None


@pytest.mark.asyncio
async def test_session_guard_returns_none_when_resolver_misses() -> None:
    from arvel.http.auth import SessionGuard

    resolver = _FakeResolver({})
    guard = SessionGuard(resolver=resolver)
    request = _FakeRequest(session=_FakeSession({"_auth_id": "u-1"}))

    user = await guard.user(request)
    assert user is None
