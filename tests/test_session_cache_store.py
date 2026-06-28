"""HTTP (doc 04) — distributed session: StartSession persists request.session over a CacheRepository."""

from __future__ import annotations

from typing import Any

from arvel.cache import CacheManager
from arvel.http.middleware import StartSession


class Req:
    def __init__(self, sid: str | None) -> None:
        self._sid = sid
        self.session: dict[str, Any] = {}

    def cookie(self, name: str) -> str | None:
        # name-agnostic: serves the one session cookie under whatever name is asked (session/__Host-)
        return self._sid


def _array_cache() -> Any:
    return CacheManager().driver("array")


async def _bump(req: Any) -> str:
    req.session["count"] = req.session.get("count", 0) + 1
    return "ok"


async def test_session_persists_across_requests_via_cache() -> None:
    cache = _array_cache()
    mw = StartSession(cache=cache)

    r1 = Req("sid-abc")
    await mw.handle(r1, _bump)
    assert r1.session["count"] == 1

    r2 = Req("sid-abc")  # same session cookie
    await mw.handle(r2, _bump)
    assert r2.session["count"] == 2  # loaded from cache, incremented


async def test_two_instances_share_session_store() -> None:
    cache = _array_cache()
    a, b = StartSession(cache=cache), StartSession(cache=cache)
    await a.handle(Req("sid-x"), _bump)
    r = Req("sid-x")
    await b.handle(r, _bump)
    assert r.session["count"] == 2  # second worker sees the first's write


async def test_distinct_sessions_isolated() -> None:
    cache = _array_cache()
    mw = StartSession(cache=cache)
    await mw.handle(Req("sid-1"), _bump)
    r = Req("sid-2")
    await mw.handle(r, _bump)
    assert r.session["count"] == 1  # different cookie → own session
