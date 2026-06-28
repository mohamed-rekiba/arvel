"""HTTP (doc 04/13) — maintenance mode stores its flag in the default cache + a 503 guard."""

from __future__ import annotations

from typing import Any

from arvel.cache import CacheManager
from arvel.http import maintenance as m
from arvel.http.maintenance import PreventRequestsDuringMaintenance
from arvel.kernel import Application, set_application


def _app_with_cache() -> Application:
    app = Application()
    app.instance("cache", CacheManager())  # default 'array' driver, isolated per test
    set_application(app)
    return app


async def test_down_up_via_default_cache() -> None:
    _app_with_cache()
    try:
        assert await m.is_down() is False
        await m.down("Back at 5", retry=90)
        assert await m.is_down() is True
        assert await m.payload() == {"message": "Back at 5", "retry": 90}
        await m.up()
        assert await m.is_down() is False
        await m.up()  # idempotent
    finally:
        set_application(None)


async def test_middleware_passes_through_when_up() -> None:
    _app_with_cache()
    try:
        await m.up()

        async def _next(req: Any) -> str:
            return "ok"

        assert await PreventRequestsDuringMaintenance().handle(object(), _next) == "ok"
    finally:
        set_application(None)


async def test_middleware_returns_503_when_down() -> None:
    _app_with_cache()
    try:
        await m.down("Soon", retry=30)

        async def _next(req: Any) -> str:  # must NOT run during maintenance
            raise AssertionError("handler ran during maintenance")

        resp = await PreventRequestsDuringMaintenance().handle(object(), _next)
        assert resp.status == 503
        assert resp.headers["Retry-After"] == "30"
        assert resp.content == {"message": "Soon"}
    finally:
        set_application(None)
