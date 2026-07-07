"""3.3 http-throttle-atomic — the named-limiter check is atomic (increment-then-compare via
CacheRepository.increment_with_ttl), so a concurrent burst at exactly the limit lets through
exactly N requests, not more. Test-first."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from arvel.cache import CacheManager
from arvel.http.middleware import MethodOverride, ThrottleRequests
from arvel.http.rate_limiter import Limit, RateLimiter
from arvel.http.response import Response
from arvel.kernel import Application, set_application


@dataclass
class FakeRequest:
    addr: str = "1.2.3.4"

    def ip(self) -> str:
        return self.addr


async def _ok(_req: Any) -> str:
    return "ok"


def _app_with_array_cache() -> Application:
    app = Application()
    cache = CacheManager().driver("array")
    app.instance("cache", cache)
    app.instance("limiter", RateLimiter(cache))
    return app


async def test_concurrent_burst_lets_exactly_n_through() -> None:
    app = _app_with_array_cache()
    set_application(app)
    n = 10
    app.make("limiter").for_("burst", lambda request: Limit.per_minute(n))
    try:

        async def call() -> Any:
            return await ThrottleRequests(limiter_name="burst").handle(FakeRequest(), _ok)

        results = await asyncio.gather(*(call() for _ in range(n * 3)))
        passed = [r for r in results if r == "ok"]
        blocked = [r for r in results if isinstance(r, Response)]
        assert len(passed) == n
        assert len(blocked) == n * 3 - n
        assert all(r.status == 429 for r in blocked)
    finally:
        set_application(None)


async def test_concurrent_burst_headers_stay_correct() -> None:
    app = _app_with_array_cache()
    set_application(app)
    n = 5
    app.make("limiter").for_("burst2", lambda request: Limit.per_minute(n))
    try:

        async def call() -> Any:
            return await ThrottleRequests(limiter_name="burst2").handle(FakeRequest(), _ok)

        results = await asyncio.gather(*(call() for _ in range(n * 2)))
        blocked = [r for r in results if isinstance(r, Response)]
        assert len(blocked) == n
        for r in blocked:
            assert r.headers["X-RateLimit-Limit"] == str(n)
            assert r.headers["X-RateLimit-Remaining"] == "0"
            assert int(r.headers["Retry-After"]) >= 0
    finally:
        set_application(None)


# --- MethodOverride vs oversized bodies --------------------------------------------------


class _CountingReceive:
    """Instrumented ASGI ``receive`` — records how many times it was called, so a test can
    assert the body was never touched when the request is refused up-front."""

    def __init__(self, body: bytes) -> None:
        self._body = body
        self.calls = 0

    async def __call__(self) -> dict[str, Any]:
        self.calls += 1
        return {"type": "http.request", "body": self._body, "more_body": False}


async def _collect_send() -> tuple[list[dict[str, Any]], Any]:
    sent: list[dict[str, Any]] = []

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    return sent, send


def _form_scope(*, content_length: int) -> dict[str, Any]:
    return {
        "type": "http",
        "method": "POST",
        "headers": [
            (b"content-type", b"application/x-www-form-urlencoded"),
            (b"content-length", str(content_length).encode("latin-1")),
        ],
    }


async def test_oversized_content_length_refused_before_body_is_read() -> None:
    receive = _CountingReceive(b"_method=PUT")
    sent, send = await _collect_send()

    async def inner_app(scope: Any, receive: Any, send: Any) -> None:
        raise AssertionError("inner app must not be reached for an oversized body")

    mw = MethodOverride(inner_app)
    await mw(_form_scope(content_length=20 * 1024 * 1024), receive, send)

    assert receive.calls == 0  # never buffered
    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 413
    assert sent[1]["type"] == "http.response.body"


async def test_under_limit_content_length_still_buffers_and_spoofs() -> None:
    receive = _CountingReceive(b"_method=PUT")
    sent, send = await _collect_send()
    reached: dict[str, Any] = {}

    async def inner_app(scope: Any, receive: Any, send: Any) -> None:
        reached["method"] = scope["method"]
        message = await receive()
        reached["body"] = message["body"]

    mw = MethodOverride(inner_app)
    await mw(_form_scope(content_length=len(b"_method=PUT")), receive, send)

    assert receive.calls == 1
    assert reached["method"] == "PUT"
    assert reached["body"] == b"_method=PUT"
    assert sent == []  # the inner app didn't send anything in this fake
