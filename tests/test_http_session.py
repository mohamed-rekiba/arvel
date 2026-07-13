"""HTTP (doc 04) — StartSession web-group middleware. Test-first."""

from __future__ import annotations

from typing import Any

import pytest

from arvel.http.middleware import SessionSettings, StartSession


def test_session_settings_reads_and_validates_config() -> None:
    import msgspec

    from arvel.kernel import Application, set_application

    app = Application()
    app.make("config").set("session", {"lifetime": "3600", "secure": "false"})
    set_application(app)
    try:
        s = SessionSettings()
        assert s.lifetime == 3600  # coerced str → int
        assert s.secure is False  # coerced str → bool
        assert s.host_prefix is None  # unset → derives from secure at the middleware
        app.make("config").set("session.lifetime", "not-an-int")
        with pytest.raises(msgspec.ValidationError):
            SessionSettings()  # bad lifetime fails fast
    finally:
        set_application(None)


class FakeRequest:
    def __init__(self, session_id: str | None = None) -> None:
        self._sid = session_id
        self.session: dict[str, Any] | None = None

    def cookie(self, name: str, default: str | None = None) -> str | None:
        # name-agnostic: these tests exercise storage mechanics, not the cookie name (session vs __Host-)
        return self._sid if self._sid is not None else default


async def test_session_attached_and_persisted() -> None:
    store: dict[str, dict[str, Any]] = {}
    middleware = StartSession(store=store)
    request = FakeRequest(session_id="abc")

    async def destination(req: Any) -> str:
        req.session["count"] = 1
        return "ok"

    assert await middleware.handle(request, destination) == "ok"
    assert store["abc"] == {"count": 1}  # mutation persisted to the store


async def test_existing_session_loaded() -> None:
    store: dict[str, dict[str, Any]] = {"abc": {"user_id": 7}}
    middleware = StartSession(store=store)
    request = FakeRequest(session_id="abc")
    seen: dict[str, Any] = {}

    async def destination(req: Any) -> str:
        seen.update(req.session)
        return "ok"

    await middleware.handle(request, destination)
    assert seen == {"user_id": 7}  # prior session state visible to the handler


async def test_missing_cookie_starts_fresh_session() -> None:
    store: dict[str, dict[str, Any]] = {}
    middleware = StartSession(store=store)
    request = FakeRequest(session_id=None)

    async def destination(req: Any) -> str:
        assert req.session == {}  # a brand-new empty session
        req.session["seen"] = True
        return "ok"

    await middleware.handle(request, destination)
    assert len(store) == 1  # one new session bucket created


class _FakeResponse:
    def __init__(self) -> None:
        self.cookies: list[tuple[str, str, dict[str, Any]]] = []

    def set_cookie(self, key: str, value: str, **kw: Any) -> None:
        self.cookies.append((key, value, kw))


async def test_lifetime_is_minutes_converted_to_seconds_for_cookie_and_ttl() -> None:
    """`session.lifetime` is in MINUTES; cookie max-age + cache TTL are seconds = lifetime x 60."""
    from arvel.kernel import Application, set_application

    app = Application()
    app.make("config").set("session", {"lifetime": 120, "secure": False})  # 120 min = 2h
    set_application(app)
    try:
        store: dict[str, dict[str, Any]] = {}
        mw = StartSession(store=store)
        request = FakeRequest(session_id=None)

        async def destination(req: Any) -> str:
            req.session["k"] = "v"
            return "ok"

        await mw.handle(request, destination)
        resp = _FakeResponse()
        await mw.terminate(request, resp)
        assert resp.cookies[0][2]["max_age"] == 7200  # cookie max-age: 120 x 60

        # the cache-TTL sink uses the same seconds value
        class _FakeCache:
            def __init__(self) -> None:
                self.ttl: int | None = None

            async def get(self, key: str) -> Any:
                return None

            async def put(self, key: str, value: Any, ttl: int | None = None) -> None:
                self.ttl = ttl

        cache = _FakeCache()
        await StartSession(cache=cache).handle(FakeRequest(session_id=None), destination)
        assert cache.ttl == 7200  # cache TTL: 120 x 60

        assert StartSession(store={}, lifetime=30)._max_age == 1800  # explicit arg is minutes too
    finally:
        set_application(None)
