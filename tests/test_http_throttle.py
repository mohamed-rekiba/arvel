"""HTTP (doc 04) — ThrottleRequests api-group middleware. Test-first."""

from __future__ import annotations

from typing import Any

import pytest

from arvel.http.middleware import ThrottleRequests
from arvel.validation import ValidationException


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
    with pytest.raises(ValidationException) as exc:
        await throttle.handle(request, _ok)  # 3 → over the limit
    assert exc.value.status == 429


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
    # The in-process limiter state is process-global (correct for one running app, but it leaks
    # across app instances built within a single test process). reset_rate_limiter() clears it so
    # each test starts fresh — without it the api throttle 429s spuriously mid-suite.
    from arvel.http import reset_rate_limiter

    throttle = ThrottleRequests(max_attempts=1, decay_seconds=60, name="t-reset-helper")
    request = FakeRequest("9.9.9.9")
    assert await throttle.handle(request, _ok) == "ok"  # 1 (at the limit)
    with pytest.raises(ValidationException):
        await throttle.handle(request, _ok)  # 2 → 429

    reset_rate_limiter()  # clear the global window state

    assert await throttle.handle(request, _ok) == "ok"  # allowed again after reset


def test_reset_sessions_clears_the_in_process_session_store() -> None:
    from arvel.http import reset_sessions
    from arvel.http.middleware import _SESSIONS

    _SESSIONS["sid-1"] = {"user_id": 7}
    reset_sessions()
    assert _SESSIONS == {}
