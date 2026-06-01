"""
SessionGuard refactored to use Arvel SessionData.
Tests import from arvel.auth.guards.session, which doesn't exist yet → red state.
"""

from __future__ import annotations

from typing import Any

import pytest


class _FakeSessionData:
    """Minimal SessionData stub."""

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


class _FakeRequest:
    def __init__(self, session: _FakeSessionData | None = None) -> None:
        self.state = type("State", (), {"session": session or _FakeSessionData()})()


class _FakeResolver:
    def __init__(self, users: dict[str, Any] | None = None) -> None:
        self._users = users or {}

    async def by_id(self, user_id: str) -> Any | None:
        return self._users.get(user_id)

    async def by_credentials(self, credentials: dict[str, object]) -> Any | None:
        return self._users.get(str(credentials.get("email")))


# user() reads from request.state.session


@pytest.mark.asyncio
async def test_session_guard_reads_user_from_state_session() -> None:
    from arvel.auth.guards.session import SessionGuard

    session = _FakeSessionData({"_auth_id": "u1"})
    request = _FakeRequest(session)
    resolver = _FakeResolver({"u1": {"id": "u1", "email": "a@example.com"}})
    guard = SessionGuard(resolver=resolver)

    user = await guard.user(request)
    assert user == {"id": "u1", "email": "a@example.com"}


@pytest.mark.asyncio
async def test_session_guard_returns_none_when_session_has_no_id() -> None:
    from arvel.auth.guards.session import SessionGuard

    request = _FakeRequest(_FakeSessionData({}))
    guard = SessionGuard(resolver=_FakeResolver())

    assert await guard.user(request) is None


@pytest.mark.asyncio
async def test_session_guard_returns_none_when_user_not_found() -> None:
    from arvel.auth.guards.session import SessionGuard

    session = _FakeSessionData({"_auth_id": "missing"})
    request = _FakeRequest(session)
    guard = SessionGuard(resolver=_FakeResolver({}))

    assert await guard.user(request) is None


# login() writes id + regenerates session


@pytest.mark.asyncio
async def test_session_guard_login_stores_user_id_in_session() -> None:
    from arvel.auth.guards.session import SessionGuard

    session = _FakeSessionData()
    request = _FakeRequest(session)
    guard = SessionGuard(resolver=_FakeResolver())

    class _User:
        id = "u1"

    await guard.login(_User(), request)
    assert session.get("_auth_id") == "u1"


@pytest.mark.asyncio
async def test_session_guard_login_regenerates_session_to_prevent_fixation() -> None:
    from arvel.auth.guards.session import SessionGuard

    session = _FakeSessionData()
    request = _FakeRequest(session)
    guard = SessionGuard(resolver=_FakeResolver())

    class _User:
        id = "u1"

    await guard.login(_User(), request)
    assert session.regenerated is True


# logout() clears session key


@pytest.mark.asyncio
async def test_session_guard_logout_removes_user_id() -> None:
    from arvel.auth.guards.session import SessionGuard

    session = _FakeSessionData({"_auth_id": "u1"})
    request = _FakeRequest(session)
    guard = SessionGuard(resolver=_FakeResolver())

    await guard.logout(request)
    assert session.get("_auth_id") is None


@pytest.mark.asyncio
async def test_session_guard_attempt_succeeds_and_logs_in() -> None:
    from arvel.auth.guards.session import SessionGuard
    from arvel.facades.hash import Hash

    plain = "correct-password"
    hashed = Hash.make(plain)
    user = {"id": "u1", "email": "a@example.com", "password": hashed}
    resolver = _FakeResolver({"a@example.com": user})
    session = _FakeSessionData()
    request = _FakeRequest(session)
    guard = SessionGuard(resolver=resolver)

    ok = await guard.attempt({"email": "a@example.com", "password": plain}, request)
    assert ok is True


@pytest.mark.asyncio
async def test_session_guard_attempt_fails_when_resolver_returns_none() -> None:
    from arvel.auth.guards.session import SessionGuard

    resolver = _FakeResolver({})
    guard = SessionGuard(resolver=resolver)

    ok = await guard.attempt({"email": "nobody@example.com"}, _FakeRequest())
    assert ok is False


# session_key is configurable


@pytest.mark.asyncio
async def test_session_guard_custom_session_key() -> None:
    from arvel.auth.guards.session import SessionGuard

    session = _FakeSessionData({"custom_key": "u5"})
    request = _FakeRequest(session)
    resolver = _FakeResolver({"u5": {"id": "u5"}})
    guard = SessionGuard(resolver=resolver, session_key="custom_key")

    user = await guard.user(request)
    assert user == {"id": "u5"}


# raises if request.state has no session


@pytest.mark.asyncio
async def test_session_guard_returns_none_when_request_has_no_state_session() -> None:
    from arvel.auth.guards.session import SessionGuard

    class _NoSessionRequest:
        class state:  # noqa: N801
            pass  # no .session attribute

    guard = SessionGuard(resolver=_FakeResolver())
    result = await guard.user(_NoSessionRequest())
    assert result is None
