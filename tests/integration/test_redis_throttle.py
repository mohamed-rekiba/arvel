"""Integration (doc 04/16) — distributed throttling shares a counter across instances on Redis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from arvel.cache import CacheManager
from arvel.http.middleware import ThrottleRequests
from arvel.validation import ValidationException

pytestmark = pytest.mark.integration


@dataclass
class Req:
    def ip(self) -> str:
        return "9.9.9.9"


async def _ok(_req: Any) -> str:
    return "ok"


async def test_distributed_throttle_over_redis(redis_url: str, configure_app: Any) -> None:
    import uuid

    app = configure_app(cache={"default": "redis", "url": redis_url})
    cache = CacheManager(app).driver("redis")
    name = f"it-{uuid.uuid4().hex[:8]}"  # unique window so reruns don't collide
    a = ThrottleRequests(max_attempts=2, decay_seconds=30, name=name, cache=cache)
    b = ThrottleRequests(max_attempts=2, decay_seconds=30, name=name, cache=cache)

    assert await a.handle(Req(), _ok) == "ok"
    assert await b.handle(Req(), _ok) == "ok"  # shared Redis counter now at 2
    with pytest.raises(ValidationException) as exc:
        await a.handle(Req(), _ok)  # 3rd across instances → 429
    assert exc.value.status == 429
