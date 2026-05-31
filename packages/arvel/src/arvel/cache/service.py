"""CacheService — round-trips a sentinel key so the cache shows up in ``/_health``."""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.services import BaseService, HealthResult, HealthStatus

if TYPE_CHECKING:
    from arvel.cache import CacheManager

_HEALTH_KEY = "__arvel_health__"


class CacheService(BaseService):
    name = "cache"

    def __init__(self, manager: CacheManager) -> None:
        self._manager = manager

    async def health_check(self) -> HealthResult:
        store = self._manager.store()
        await store.put(_HEALTH_KEY, "ok", ttl=5)
        value = await store.get(_HEALTH_KEY)
        if value != "ok":
            return HealthResult(HealthStatus.degraded, "cache round-trip mismatch")
        return HealthResult(HealthStatus.healthy)


__all__ = ["CacheService"]
