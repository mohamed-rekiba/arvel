"""HTTP (doc 04) — ThrottleRequests api-group middleware. Test-first."""

from __future__ import annotations

from typing import Any

import pytest
from litestar.testing import TestClient

from arvel.http import HttpKernel, reset_rate_limiter
from arvel.http.exceptions import HttpException
from arvel.http.middleware import ThrottleRequests
from arvel.routing import Router


def test_throttled_route_returns_429_with_rate_limit_headers() -> None:
    # real HTTP stack: a route in a throttled group, driven past the limit through TestClient
    reset_rate_limiter()
    router = Router()
    router.get("/ping", _ok).middleware(ThrottleRequests(max_attempts=2, decay_seconds=60, name="p"))
    kernel = HttpKernel()
    router.apply_to(kernel)
    with TestClient(kernel.build()) as client:
        assert client.get("/ping").status_code == 200
        assert client.get("/ping").status_code == 200
        blocked = client.get("/ping")
        assert blocked.status_code == 429
        assert int(blocked.headers["retry-after"]) > 0
        assert blocked.headers["x-ratelimit-limit"] == "2"
        assert blocked.headers["x-ratelimit-remaining"] == "0"
        assert "x-ratelimit-reset" in blocked.headers


class FakeRequest:
    def __init__(self, ip: str = "1.2.3.4") -> None:
        self._ip = ip

    def ip(self) -> str:
        return self._ip


async def _ok(_request: Any) -> str:
    return "ok"


async def test_allows_up_to_limit_then_429() -> None:
    throttle = ThrottleRequests(max_attempts=2, decay_seconds=60, name="t-limit")
    request = FakeRequest()
    assert await throttle.handle(request, _ok) == "ok"  # 1
    assert await throttle.handle(request, _ok) == "ok"  # 2
    with pytest.raises(HttpException) as exc:
        await throttle.handle(request, _ok)  # 3 → over the limit
    assert exc.value.status == 429
    assert exc.value.response_headers["Retry-After"]
    assert exc.value.response_headers["X-RateLimit-Remaining"] == "0"


async def test_separate_clients_have_separate_buckets() -> None:
    throttle = ThrottleRequests(max_attempts=1, decay_seconds=60, name="t-clients")
    assert await throttle.handle(FakeRequest("10.0.0.1"), _ok) == "ok"
    assert (
        await throttle.handle(FakeRequest("10.0.0.2"), _ok) == "ok"
    )  # different client, own bucket


async def test_window_reset_allows_again() -> None:
    throttle = ThrottleRequests(max_attempts=1, decay_seconds=0, name="t-reset")
    request = FakeRequest()
    assert await throttle.handle(request, _ok) == "ok"
    assert await throttle.handle(request, _ok) == "ok"  # decay 0 → window resets every call


async def test_reset_rate_limiter_clears_state_for_test_isolation() -> None:
    # limiter state is process-global and leaks across app instances within one test process
    from arvel.http import reset_rate_limiter

    throttle = ThrottleRequests(max_attempts=1, decay_seconds=60, name="t-reset-helper")
    request = FakeRequest("9.9.9.9")
    assert await throttle.handle(request, _ok) == "ok"  # 1 (at the limit)
    with pytest.raises(HttpException):
        await throttle.handle(request, _ok)  # 2 → 429

    reset_rate_limiter()

    assert await throttle.handle(request, _ok) == "ok"


def test_reset_sessions_clears_the_in_process_session_store() -> None:
    from arvel.http import reset_sessions
    from arvel.http.middleware import _SESSIONS

    _SESSIONS["sid-1"] = {"user_id": 7}
    reset_sessions()
    assert _SESSIONS == {}
