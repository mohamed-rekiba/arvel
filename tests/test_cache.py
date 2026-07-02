"""Phase 6 — Cache manager (cashews-backed) behaviour."""

from __future__ import annotations

from typing import Any

import pytest

from arvel.cache import CacheManager
from arvel.support.manager import MissingExtraError


def _cache() -> Any:
    return CacheManager().driver()


async def test_put_get_forget() -> None:
    cache = _cache()
    assert await cache.put("k", "v")
    assert await cache.get("k") == "v"
    assert await cache.has("k")
    await cache.forget("k")
    assert await cache.get("k", "default") == "default"


async def test_remember_computes_once() -> None:
    cache = _cache()
    calls = {"n": 0}

    async def compute() -> int:
        calls["n"] += 1
        return 42

    assert await cache.remember("stat", 60, compute) == 42
    assert await cache.remember("stat", 60, compute) == 42  # served from cache
    assert calls["n"] == 1


async def test_redis_driver_fails_loudly_when_backend_is_down() -> None:
    """A dead Redis must RAISE, not silently no-op (Laravel parity). cashews' Redis backend
    defaults ``suppress=True`` — get→None / put→no-op / a Cache.lock that isn't a lock — which
    turns an infra outage into silent data-correctness bugs (surfaced by the kit's S1 tier)."""
    pytest.importorskip("cashews.backends.redis")
    from cashews.exceptions import CacheBackendInteractionError

    from arvel.kernel import Application, set_application

    app = Application()
    app.make("config").set(
        "cache", {"default": "redis", "url": "redis://127.0.0.1:9/0"}  # discard port — dead
    )
    set_application(app)
    try:
        cache = CacheManager(app=app).driver()
        with pytest.raises(CacheBackendInteractionError):
            await cache.put("k", "v")
    finally:
        set_application(None)


def test_manager_forwards_to_default_driver() -> None:
    manager = CacheManager()
    # __getattr__ proxy: manager.lock resolves on the default driver
    assert manager.default_driver() == "array"
    assert callable(manager.lock)


def test_missing_driver_raises_missing_extra() -> None:
    manager = CacheManager()
    with pytest.raises(MissingExtraError):
        manager.driver("dynamodb")


def test_extend_registers_custom_driver() -> None:
    manager = CacheManager()
    sentinel = object()
    manager.extend("custom", lambda _app: sentinel)
    assert manager.driver("custom") is sentinel
