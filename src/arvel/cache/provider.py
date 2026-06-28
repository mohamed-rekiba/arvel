"""CacheServiceProvider — binds the Cache manager (auto-discovered)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.cache import CacheManager
from arvel.kernel.service_provider import ServiceProvider

if TYPE_CHECKING:
    from arvel.contracts import Container


class CacheServiceProvider(ServiceProvider):
    def register(self) -> None:
        def make_cache(app: Container) -> CacheManager:
            return CacheManager(app)

        self.app.singleton("cache", make_cache)

    def boot(self) -> None:
        """No-op."""
