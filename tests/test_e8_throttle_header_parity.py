"""E8/H14 — throttle unification (DR-0041, revised): one cache-TTL window, one 429 decision —
a custom ``Limit.response(callback)`` wins, else ``HttpException(429)`` is raised carrying the
rate-limit headers so ``render_exception`` content-negotiates the body like every other framework
error. Plain and named modes must produce byte-identical status + Retry-After + X-RateLimit-*
fields on their over-limit response — that parity is the regression guard for the storage-engine
swap (monotonic dict -> array-cache RateLimiter). Driven through the real HTTP test client
(spec: projects/arvel/specs/E8-kernel-throttle-url.md)."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from typing import Any

from litestar.testing import TestClient

from arvel.cache import CacheManager
from arvel.http import HttpKernel, reset_rate_limiter
from arvel.http.middleware import ThrottleRequests
from arvel.http.rate_limiter import Limit, RateLimiter
from arvel.kernel import Application, set_application
from arvel.routing import Router

_PARITY_HEADERS = ("retry-after", "x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset")


async def _ok(request: Any) -> dict[str, bool]:
    return {"ok": True}


@contextlib.contextmanager
def _client() -> Iterator[TestClient[Any]]:
    reset_rate_limiter()
    app = Application()
    app.instance("cache", CacheManager(app))
    app.instance("limiter", RateLimiter(app.make("cache")))
    app.make("limiter").for_("parity", lambda request: Limit.per_minute(1))
    app.make("limiter").for_("parity-negotiate", lambda request: Limit.per_minute(1))
    app.make("limiter").for_(
        "parity-cb", lambda request: Limit.per_minute(1).response(lambda req: {"nope": True})
    )

    router = Router()
    router.get("/plain", _ok).middleware(
        ThrottleRequests(max_attempts=1, decay_seconds=60, name="parity-plain")
    )
    router.get("/named", _ok).middleware("throttle:parity")
    router.get("/named-negotiate", _ok).middleware("throttle:parity-negotiate")
    router.get("/named-cb", _ok).middleware("throttle:parity-cb")

    kernel = HttpKernel(app=app)
    router.apply_to(kernel)
    # the `throttle:<name>` resolver reads the GLOBAL app context, not `kernel.app` directly
    set_application(app)
    try:
        with TestClient(kernel.as_asgi()) as client:
            yield client
    finally:
        set_application(None)


def test_plain_and_named_429_headers_are_field_by_field_identical() -> None:
    with _client() as client:
        assert client.get("/plain").status_code == 200
        plain_blocked = client.get("/plain")
        assert plain_blocked.status_code == 429

        assert client.get("/named").status_code == 200
        named_blocked = client.get("/named")
        assert named_blocked.status_code == 429

        for header in _PARITY_HEADERS:
            assert header in plain_blocked.headers
            assert header in named_blocked.headers
            assert plain_blocked.headers[header] == named_blocked.headers[header], (
                f"{header} diverged: plain={plain_blocked.headers[header]!r} "
                f"named={named_blocked.headers[header]!r}"
            )
        assert plain_blocked.headers["x-ratelimit-limit"] == "1"
        assert plain_blocked.headers["x-ratelimit-remaining"] == "0"
        assert int(plain_blocked.headers["retry-after"]) > 0


def test_custom_response_callback_still_wins_over_the_default_429() -> None:
    with _client() as client:
        assert client.get("/named-cb").json() == {"ok": True}
        blocked = client.get("/named-cb")
        # the callback's own return value passes straight through the funnel — not a 429
        assert blocked.json() == {"nope": True}


def test_named_mode_body_is_now_content_negotiated_the_one_intended_change() -> None:
    """DR-0041's sole intended delta: named mode's no-callback 429 body used to be always-JSON;
    it now content-negotiates like every other framework error (422/403/404/…)."""
    with _client() as client:
        assert client.get("/named-negotiate").status_code == 200

        html = client.get("/named-negotiate", headers={"Accept": "text/html"})
        assert html.status_code == 429
        assert "text/html" in html.headers["content-type"]
        assert b"429" in html.content

        api = client.get("/named-negotiate", headers={"Accept": "application/json"})
        assert api.status_code == 429
        assert "application/json" in api.headers["content-type"]
        assert api.json()["message"]
        # parity fields survive negotiation on both branches
        assert html.headers["x-ratelimit-limit"] == api.headers["x-ratelimit-limit"] == "1"
