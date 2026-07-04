"""CacheServiceProvider — binds the Cache manager + the Redis facade manager (auto-discovered)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from arvel.cache import CacheManager
from arvel.kernel.service_provider import ServiceProvider

if TYPE_CHECKING:
    from arvel.contracts import Container


class CacheServiceProvider(ServiceProvider):
    def register(self) -> None:
        def make_cache(app: Container) -> CacheManager:
            return CacheManager(app)

        self.app.singleton("cache", make_cache)

        def make_redis(app: Container) -> Any:
            from arvel.cache.redis import RedisManager

            return RedisManager(app)

        self.app.singleton("redis", make_redis)

    def boot(self) -> None:
        # Graceful shutdown: close pooled redis connections when the app terminates.
        app = self.app

        async def close_redis() -> None:
            if app.bound("redis"):
                await app.make("redis").close_all()

        app.terminating(close_redis)
