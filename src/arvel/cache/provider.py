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
        # Register the cache as a health-checked resource (DR-0039). It owns its lifecycle — a redis
        # PING for connect/check, and disconnect drains the pooled redis + cache-lock clients — so
        # the teardown lives with the resource instead of a standalone terminating hook.
        app = self.app
        from arvel.cache import CacheSettings
        from arvel.cache.resource import CacheResource

        driver = CacheSettings().default
        critical = bool(app.config("cache.critical", False))
        app.resources.register(
            CacheResource(driver, app.make("redis"), app.make("cache"), critical=critical)
        )
