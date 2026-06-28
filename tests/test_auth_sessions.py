"""Auth (L8) — per-user session generation: 'log out other devices' for live sessions."""

from __future__ import annotations

from typing import Any

from arvel.auth.sessions import (
    GEN_KEY,
    EnsureSessionCurrent,
    current_generation,
    invalidate_all_sessions,
    logout_other_sessions,
    session_is_current,
    stamp_session,
)


class _FakeCache:
    """Minimal CacheRepository double: get + atomic increment over a dict."""

    def __init__(self) -> None:
        self.store: dict[str, int] = {}

    async def get(self, key: str, default: Any = None) -> Any:
        return self.store.get(key, default)

    async def increment(self, key: str, by: int = 1) -> int:
        self.store[key] = self.store.get(key, 0) + by
        return self.store[key]


class _Req:
    def __init__(self, session: dict[str, Any]) -> None:
        self.session = session


async def _ok(_req: Any) -> str:
    return "ok"


# --- generation primitives ----------------------------------------------------


async def test_stamp_and_current_match() -> None:
    cache = _FakeCache()
    session: dict[str, Any] = {}
    await stamp_session(session, 1, cache=cache)
    assert session[GEN_KEY] == 0  # no bumps yet
    assert await session_is_current(session, 1, cache=cache) is True


async def test_unstamped_session_is_treated_current() -> None:
    cache = _FakeCache()
    assert await session_is_current({"_user_id": 1}, 1, cache=cache) is True  # no GEN_KEY → keep


async def test_logout_other_sessions_keeps_current_evicts_the_rest() -> None:
    cache = _FakeCache()
    # two devices, both stamped at gen 0
    current: dict[str, Any] = {}
    other: dict[str, Any] = {}
    await stamp_session(current, 7, cache=cache)
    await stamp_session(other, 7, cache=cache)

    await logout_other_sessions(_Req(current), 7, cache=cache)

    assert await session_is_current(current, 7, cache=cache) is True  # current restamped → survives
    assert await session_is_current(other, 7, cache=cache) is False  # behind → evicted


async def test_invalidate_all_evicts_even_the_current() -> None:
    cache = _FakeCache()
    current: dict[str, Any] = {}
    await stamp_session(current, 7, cache=cache)
    await invalidate_all_sessions(7, cache=cache)  # no restamp
    assert await session_is_current(current, 7, cache=cache) is False


async def test_no_cache_is_inert_not_a_lockout() -> None:
    # no cache + no app → generation is 0, stamping/checks no-op to "current" (feature simply off)
    session: dict[str, Any] = {}
    await stamp_session(session, 1, cache=None)
    assert await session_is_current(session, 1, cache=None) is True
    assert await current_generation(1, cache=None) == 0


# --- EnsureSessionCurrent middleware ------------------------------------------


async def test_middleware_clears_auth_for_an_evicted_session() -> None:
    cache = _FakeCache()
    session: dict[str, Any] = {"_user_id": 7, "_impersonator_id": 9}
    await stamp_session(session, 7, cache=cache)
    await invalidate_all_sessions(7, cache=cache)  # session now behind

    await EnsureSessionCurrent(cache=cache).handle(_Req(session), _ok)

    assert "_user_id" not in session
    assert GEN_KEY not in session
    assert "_impersonator_id" not in session


class _BrokenCache:
    """A cache whose reads raise — to assert the fail-OPEN posture."""

    async def get(self, key: str, default: Any = None) -> Any:
        raise RuntimeError("cache down")

    async def increment(self, key: str, by: int = 1) -> int:
        raise RuntimeError("cache down")


async def test_fails_open_on_cache_error() -> None:
    # A cache outage must NOT log everyone out: a stamped session stays "current".
    session: dict[str, Any] = {"_user_id": 7, GEN_KEY: 3}
    assert await session_is_current(session, 7, cache=_BrokenCache()) is True
    assert await EnsureSessionCurrent(cache=_BrokenCache()).handle(_Req(session), _ok) == "ok"
    assert session["_user_id"] == 7  # not evicted on a cache error


async def test_middleware_keeps_a_current_session() -> None:
    cache = _FakeCache()
    session: dict[str, Any] = {"_user_id": 7}
    await stamp_session(session, 7, cache=cache)
    assert await EnsureSessionCurrent(cache=cache).handle(_Req(session), _ok) == "ok"
    assert session["_user_id"] == 7  # untouched
