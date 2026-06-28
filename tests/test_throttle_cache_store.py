"""HTTP (doc 04) — distributed throttle: ThrottleRequests counts over a CacheRepository."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from arvel.cache import CacheManager
from arvel.http.middleware import ThrottleRequests
from arvel.validation import ValidationException


@dataclass
class Req:
    addr: str = "1.2.3.4"

    def ip(self) -> str:
        return self.addr


async def _ok(_req: Any) -> str:
    return "ok"


def _array_cache() -> Any:
    return CacheManager().driver("array")


async def test_cache_backed_allows_then_blocks() -> None:
    cache = _array_cache()
    mw = ThrottleRequests(max_attempts=3, decay_seconds=60, name="api", cache=cache)
    for _ in range(3):
        assert await mw.handle(Req(), _ok) == "ok"
    with pytest.raises(ValidationException) as exc:
        await mw.handle(Req(), _ok)
    assert exc.value.status == 429


async def test_two_instances_share_the_cache_store() -> None:
    # distributed: separate middleware instances (≈ separate workers) over one shared cache
    cache = _array_cache()
    a = ThrottleRequests(max_attempts=2, decay_seconds=60, name="api", cache=cache)
    b = ThrottleRequests(max_attempts=2, decay_seconds=60, name="api", cache=cache)
    assert await a.handle(Req(), _ok) == "ok"
    assert await b.handle(Req(), _ok) == "ok"
    with pytest.raises(ValidationException):
        await a.handle(Req(), _ok)  # 3rd hit across both instances → blocked


async def test_distinct_clients_independent() -> None:
    cache = _array_cache()
    mw = ThrottleRequests(max_attempts=1, decay_seconds=60, name="api", cache=cache)
    assert await mw.handle(Req("10.0.0.1"), _ok) == "ok"
    assert await mw.handle(Req("10.0.0.2"), _ok) == "ok"  # different client, own counter
    with pytest.raises(ValidationException):
        await mw.handle(Req("10.0.0.1"), _ok)
