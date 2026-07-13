"""Coverage — Cache manager edge paths (remember/lock/config/redis build)."""

from __future__ import annotations

from arvel.cache import CacheManager


async def test_remember_and_lock() -> None:
    cache = CacheManager().driver()
    calls = {"n": 0}

    async def compute() -> int:
        calls["n"] += 1
        return 7

    assert await cache.remember("k", 60, compute) == 7
    assert await cache.remember("k", 60, compute) == 7  # cached → compute once
    assert calls["n"] == 1
    assert await cache.remember_forever("kf", lambda: 9) == 9
    async with cache.lock("L", seconds=5):
        pass  # atomic lock context manager


def test_default_driver_from_config() -> None:
    from arvel.cache import CacheSettings
    from arvel.kernel import Application, set_application

    app = Application()
    app.make("config").set("cache", {"default": "redis", "url": "redis://h:6379/1"})
    set_application(app)  # config() is the single source of truth (DR-0016)
    try:
        assert CacheManager(app).default_driver() == "redis"
        assert CacheSettings().url == "redis://h:6379/1"
    finally:
        set_application(None)


def test_cache_settings_defaults_without_app() -> None:
    from arvel.cache import CacheSettings
    from arvel.kernel import set_application

    set_application(None)
    s = CacheSettings()
    assert s.default == "array"
    assert s.url == "redis://localhost:6379/0"
