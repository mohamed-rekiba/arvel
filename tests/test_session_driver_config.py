"""SessionSettings.driver == "redis" auto-wires StartSession to the app's own bound "cache"
service (HttpKernel.use_default_groups) — sessions survive restarts and are shared across every
worker/host, instead of StartSession's in-process dict default. Anything else (including the
unset default) keeps that existing default unchanged."""

from __future__ import annotations

from typing import Any

from arvel.cache.provider import CacheServiceProvider
from arvel.http import HttpKernel
from arvel.http.middleware import ShareErrorsFromSession, StartSession, ValidateCsrfToken
from arvel.kernel import Application


def _app_with_cache(**session_config: Any) -> Application:
    app = Application()
    repo = app.make("config")
    repo.set("cache", {"default": "array"})
    repo.set("session", session_config)
    CacheServiceProvider(app).register()
    return app


def test_redis_driver_wires_cache_backed_session() -> None:
    app = _app_with_cache(driver="redis")
    kernel = HttpKernel(app=app).use_default_groups()
    session_mw = kernel.groups["web"][1]  # index 0 is EncryptCookies (H7)
    assert isinstance(session_mw, StartSession)  # a built instance, not the bare class
    assert kernel.groups["web"][2:] == [ShareErrorsFromSession, ValidateCsrfToken]


def test_default_driver_keeps_in_process_session() -> None:
    app = _app_with_cache()  # driver unset → SessionSettings default ("cookie")
    kernel = HttpKernel(app=app).use_default_groups()
    assert kernel.groups["web"][1] is StartSession  # still the bare class, unchanged


def test_redis_driver_without_bound_cache_falls_back() -> None:
    app = Application()
    app.make("config").set("session", {"driver": "redis"})  # no CacheServiceProvider registered
    kernel = HttpKernel(app=app).use_default_groups()
    assert kernel.groups["web"][1] is StartSession  # no "cache" bound → safe fallback, no crash


async def test_session_actually_persists_via_the_configured_cache() -> None:
    """End-to-end: a request through the auto-wired middleware really lands in the app's cache,
    not StartSession's own in-process dict — the thing this feature actually buys you."""
    app = _app_with_cache(driver="redis", secure=False)
    kernel = HttpKernel(app=app).use_default_groups()
    session_mw = kernel.groups["web"][1]  # index 0 is EncryptCookies (H7)

    class Req:
        def __init__(self) -> None:
            self.session: dict[str, Any] = {}

        def cookie(self, name: str) -> str | None:
            return None  # no cookie yet → a new session id is minted

    async def _set(request: Any) -> str:
        request.session["hello"] = "world"
        return "ok"

    req = Req()
    await session_mw.handle(req, _set)

    cache = app.make("cache")
    stored = await cache.get(f"session:{req._session_id}")
    assert stored == {"hello": "world"}  # really in the shared cache, not just req.session
