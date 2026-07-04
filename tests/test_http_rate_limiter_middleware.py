"""HTTP (doc 13 §1) — `throttle:<name>` route middleware over the named RateLimiter. Test-first."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from litestar.testing import TestClient

from arvel.cache import CacheManager
from arvel.http import HttpKernel
from arvel.http.middleware import ThrottleRequests
from arvel.http.rate_limiter import Limit, RateLimiter
from arvel.kernel import Application, set_application
from arvel.routing import Router


@dataclass
class FakeRequest:
    addr: str = "1.2.3.4"

    def ip(self) -> str:
        return self.addr


async def _ok(_req: Any) -> str:
    return "ok"


def _app_with_cache() -> Application:
    """A bare app with just a "cache" + "limiter" binding — the same wiring
    ``HttpKernel.use_default_groups()`` does for a served app (tested separately below)."""
    app = Application()
    app.instance("cache", CacheManager(app))
    app.instance("limiter", RateLimiter(app.make("cache")))
    return app


# --- direct unit tests (no TestClient) --------------------------------------------------


async def test_unknown_limiter_name_raises() -> None:
    app = _app_with_cache()
    set_application(app)
    try:
        mw = ThrottleRequests(limiter_name="nope")
        with pytest.raises(RuntimeError, match="nope"):
            await mw.handle(FakeRequest(), _ok)
    finally:
        set_application(None)


async def test_no_limiter_bound_raises() -> None:
    set_application(None)
    mw = ThrottleRequests(limiter_name="api")
    with pytest.raises(RuntimeError, match="limiter"):
        await mw.handle(FakeRequest(), _ok)


async def test_unlimited_resolver_passes_through() -> None:
    app = _app_with_cache()
    app.make("limiter").for_("api", lambda request: None)
    set_application(app)
    try:
        mw = ThrottleRequests(limiter_name="api")
        assert await mw.handle(FakeRequest(), _ok) == "ok"
    finally:
        set_application(None)


async def test_too_many_attempts_returns_429_response_with_headers() -> None:
    app = _app_with_cache()
    app.make("limiter").for_("api", lambda request: Limit.per_minute(2))
    set_application(app)
    try:
        mw = ThrottleRequests(limiter_name="api")
        assert await mw.handle(FakeRequest(), _ok) == "ok"
        assert await mw.handle(FakeRequest(), _ok) == "ok"

        from arvel.http.response import Response

        response = await ThrottleRequests(limiter_name="api").handle(FakeRequest(), _ok)
        assert isinstance(response, Response)
        assert response.status == 429
        assert response.headers["X-RateLimit-Limit"] == "2"
        assert response.headers["X-RateLimit-Remaining"] == "0"
        assert int(response.headers["Retry-After"]) > 0
    finally:
        set_application(None)


async def test_default_segment_is_per_user_then_per_ip() -> None:
    from arvel.support import current_user

    app = _app_with_cache()
    app.make("limiter").for_("api", lambda request: Limit.per_minute(1))
    set_application(app)

    @dataclass
    class User:
        id: int

    try:
        token = current_user.set(User(id=1))
        try:
            assert await ThrottleRequests(limiter_name="api").handle(FakeRequest(), _ok) == "ok"
        finally:
            current_user.reset(token)

        # same user, different IP -> still the SAME bucket (keyed by user id, not IP)
        token = current_user.set(User(id=1))
        try:
            from arvel.http.response import Response

            result = await ThrottleRequests(limiter_name="api").handle(FakeRequest("9.9.9.9"), _ok)
            assert isinstance(result, Response) and result.status == 429
        finally:
            current_user.reset(token)

        # a different user -> its own bucket, even from the first IP
        token = current_user.set(User(id=2))
        try:
            assert await ThrottleRequests(limiter_name="api").handle(FakeRequest(), _ok) == "ok"
        finally:
            current_user.reset(token)
    finally:
        set_application(None)


async def test_by_key_overrides_the_default_segment() -> None:
    app = _app_with_cache()
    app.make("limiter").for_("tenant", lambda request: Limit.per_minute(1).by("tenant-42"))
    set_application(app)
    try:
        # two different IPs, same explicit .by() key -> share one bucket
        assert (
            await ThrottleRequests(limiter_name="tenant").handle(FakeRequest("1.1.1.1"), _ok)
            == "ok"
        )

        from arvel.http.response import Response

        result = await ThrottleRequests(limiter_name="tenant").handle(FakeRequest("2.2.2.2"), _ok)
        assert isinstance(result, Response) and result.status == 429
    finally:
        set_application(None)


async def test_custom_response_callback_used_instead_of_default() -> None:
    app = _app_with_cache()

    def resolver(request: Any) -> Limit:
        return Limit.per_minute(1).response(lambda req: {"nope": True})

    app.make("limiter").for_("custom", resolver)
    set_application(app)
    try:
        assert await ThrottleRequests(limiter_name="custom").handle(FakeRequest(), _ok) == "ok"
        result = await ThrottleRequests(limiter_name="custom").handle(FakeRequest(), _ok)
        assert result == {"nope": True}
    finally:
        set_application(None)


async def test_success_headers_applied_in_terminate() -> None:
    app = _app_with_cache()
    app.make("limiter").for_("api", lambda request: Limit.per_minute(5))
    set_application(app)
    try:
        mw = ThrottleRequests(limiter_name="api")
        assert await mw.handle(FakeRequest(), _ok) == "ok"

        response = type("R", (), {"headers": {}})()
        await mw.terminate(FakeRequest(), response)
        assert response.headers["X-RateLimit-Limit"] == "5"
        assert response.headers["X-RateLimit-Remaining"] == "4"
    finally:
        set_application(None)


# --- end-to-end through a real scaffolded route -----------------------------------------


def test_named_limiter_end_to_end_headers_and_429() -> None:
    app = _app_with_cache()
    set_application(app)
    try:
        kernel = HttpKernel(app=app).use_default_groups()
        app.make("limiter").for_("api", lambda request: Limit.per_minute(2))

        async def _handler(request: Any) -> dict[str, str]:
            return {"ok": "1"}

        router = Router()
        router.get("/limited", _handler).middleware("throttle:api")
        router.apply_to(kernel)
        with TestClient(app=kernel.as_asgi()) as client:
            first = client.get("/limited")
            assert first.status_code == 200
            assert first.headers["X-RateLimit-Limit"] == "2"
            assert first.headers["X-RateLimit-Remaining"] == "1"

            second = client.get("/limited")
            assert second.status_code == 200
            assert second.headers["X-RateLimit-Remaining"] == "0"

            third = client.get("/limited")
            assert third.status_code == 429
            assert "Retry-After" in third.headers
            assert third.headers["X-RateLimit-Limit"] == "2"
            assert third.headers["X-RateLimit-Remaining"] == "0"
    finally:
        set_application(None)
