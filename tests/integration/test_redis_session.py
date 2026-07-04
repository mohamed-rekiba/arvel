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
