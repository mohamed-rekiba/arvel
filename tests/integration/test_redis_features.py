"""Integration (spec 20-pennant) — the ``cache`` feature-flag driver against a real Redis: a
resolved value is stored in the (tagged) cache, so ``purge`` can clear every scope for one flag in
a single ``TaggedCache.flush()`` without touching another flag's entries."""

from __future__ import annotations

from typing import Any

import pytest

from arvel.cache import CacheManager
from arvel.features import FeatureManager

pytestmark = pytest.mark.integration


def _cache_backed_manager(redis_url: str, configure_app: Any) -> FeatureManager:
    app = configure_app(cache={"default": "redis", "url": redis_url}, features={"driver": "cache"})
    # `create_cache_driver` resolves "cache" through the container (not a directly-built
    # CacheManager), so it must actually be bound here — mirrors how other cross-module drivers
    # (e.g. `scout:import`'s "search" binding in test_console_scout.py) wire a dependency manager.
    app.singleton("cache", lambda a: CacheManager(a))
    return FeatureManager(app)


async def test_cache_driver_resolves_once_and_stores_in_redis(
    redis_url: str, configure_app: Any
) -> None:
    manager = _cache_backed_manager(redis_url, configure_app)
    calls: list[str] = []

    def resolver(scope: Any) -> bool:
        calls.append(scope)
        return scope == "user-a"

    manager.define("beta", resolver)
    assert await manager.active("beta", "user-a") is True
    assert await manager.active("beta", "user-a") is True  # served from Redis, not re-run
    assert calls == ["user-a"]
    assert await manager.active("beta", "user-b") is False
    assert calls == ["user-a", "user-b"]


async def test_cache_driver_purge_clears_only_the_named_flag(
    redis_url: str, configure_app: Any
) -> None:
    manager = _cache_backed_manager(redis_url, configure_app)
    await manager.activate("beta", "user-a")
    await manager.activate("other", "user-a")

    await manager.purge("beta")

    from arvel.features import _MISSING  # pyright: ignore[reportPrivateUsage]

    assert await manager.driver().get("beta", "user-a") is _MISSING
    assert await manager.driver().get("other", "user-a") is True  # untouched
