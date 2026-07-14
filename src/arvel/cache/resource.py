"""CacheResource — the cache as a health-checkable, lifecycle-managed resource (DR-0039).

Registered by ``CacheServiceProvider``. For the ``redis`` driver ``check`` is a ``PING``; the
in-process ``array`` driver has no dependency to reach, so it always reports healthy. ``disconnect``
drains the pooled redis + cache-lock clients at shutdown — the teardown that used to be a standalone
``terminating`` callback now lives with the resource.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from arvel.contracts import HealthResult, HealthStatus

if TYPE_CHECKING:
    from arvel.cache import CacheManager


class CacheResource:
    """PING the redis cache (or trivially-OK for the in-process ``array`` driver). Non-critical: a
    cache outage degrades rather than aborts — most apps can serve, slower, without it."""

    name = "cache"

    def __init__(
        self, driver: str, redis: Any, cache: CacheManager, *, critical: bool = False
    ) -> None:
        self._driver = driver
        self._redis = redis
        self._cache = cache
        self.critical = critical

    async def connect(self) -> None:
        if self._driver == "redis":
            await self._redis.connection().command("PING")

    async def disconnect(self) -> None:
        await self._redis.close_all()
        await self._cache.close()  # drain the cache lock client(s)

    async def check(self) -> HealthResult:
        if self._driver != "redis":
            return HealthResult(HealthStatus.OK, detail=f"{self._driver} (in-process)")
        await self._redis.connection().command("PING")
        return HealthResult(HealthStatus.OK, detail="PING")
