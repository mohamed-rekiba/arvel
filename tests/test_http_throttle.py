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
