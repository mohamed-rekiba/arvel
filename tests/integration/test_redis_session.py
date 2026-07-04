"""Sessions persist across StartSession instances on real Redis."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from arvel.cache import CacheManager
from arvel.http.middleware import StartSession

pytestmark = pytest.mark.integration


class Req:
    def __init__(self, sid: str) -> None:
        self._sid = sid
        self.session: dict[str, Any] = {}

    def cookie(self, name: str) -> str | None:
        # secure=False here → no __Host- prefix on the cookie name
        return self._sid if name == "session" else None


async def _set_user(req: Any) -> str:
    req.session["user_id"] = 7
    return "ok"


async def _read_user(req: Any) -> str:
    return str(req.session.get("user_id"))


async def test_session_persists_over_redis(redis_url: str, configure_app: Any) -> None:
    app = configure_app(cache={"default": "redis", "url": redis_url})
    cache = CacheManager(app).driver("redis")
    sid = f"sid-{uuid.uuid4().hex[:8]}"

    await StartSession(cache=cache, secure=False).handle(Req(sid), _set_user)
    r = Req(sid)
    await StartSession(cache=cache, secure=False).handle(r, _read_user)
    assert r.session["user_id"] == 7


# --- 14 AUTH-SESSION: SessionGuard.login persists across requests, over real Redis -------------


class _SessGuardUser:
    def __init__(self, uid: int) -> None:
        self.id = uid


class _SessGuardReq:
    """No fixed sid — mimics a fresh browser presenting whatever cookie it was last given."""

    def __init__(self, sid: str | None) -> None:
        self._sid = sid
        self.session: dict[str, Any] = {}

    def cookie(self, name: str, default: str | None = None) -> str | None:
        return self._sid if name == "session" else default


async def test_session_guard_login_persists_across_requests_over_redis(
    redis_url: str, configure_app: Any
) -> None:
    from arvel.auth import current_user
    from arvel.auth.guards import SessionGuard

    app = configure_app(cache={"default": "redis", "url": redis_url})
    cache = CacheManager(app).driver("redis")

    req1 = _SessGuardReq(None)

    async def login(r: Any) -> str:
        await SessionGuard().login(_SessGuardUser(42), r)
        return "ok"

    token = current_user.set(None)
    try:
        await StartSession(cache=cache, secure=False).handle(req1, login)
    finally:
        current_user.reset(token)
    sid_after_login = req1._session_id  # rotated (fixation defence)

    # a SECOND, independent request presenting the rotated cookie
    req2 = _SessGuardReq(sid_after_login)

    async def read(r: Any) -> Any:
        return await SessionGuard().user_id(r)

    user_id = await StartSession(cache=cache, secure=False).handle(req2, read)
    assert user_id == 42  # persisted user id survives across the real Redis-backed store

    # logout invalidates: a third request over the OLD (rotated-away) id sees an empty session
    req3 = _SessGuardReq(sid_after_login)

    async def logout(r: Any) -> Any:
        await SessionGuard().logout(r)
        return await SessionGuard().user_id(r)

    assert await StartSession(cache=cache, secure=False).handle(req3, logout) is None
