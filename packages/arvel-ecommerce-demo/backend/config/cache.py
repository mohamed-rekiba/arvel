"""Cache configuration — mirrors ``CacheConfig`` env vars.

The framework's ``CacheServiceProvider`` reads typed settings directly
(``CACHE_CONNECTION``, ``CACHE_URL``, ``CACHE_PREFIX``). This module is the
Laravel-shaped inventory so ``lookup("cache.stores.redis.url")`` stays
discoverable alongside ``cache.py`` / ``queue.py`` / ``database.py``.
"""

from __future__ import annotations

from arvel.support.env import env

default: str = env("CACHE_CONNECTION", "redis")

stores: dict[str, dict[str, object]] = {
    "redis": {
        "driver": "redis",
        "url": env("CACHE_URL", "redis://localhost:6379/0"),
        "prefix": env("CACHE_PREFIX", "arvel-demo:cache:"),
    },
}
