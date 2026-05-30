"""CacheServiceProvider — registers the CacheManager and Cache facade."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from arvel.providers.service_provider import ServiceProvider

if TYPE_CHECKING:
    from arvel.console import Command


class CacheServiceProvider(ServiceProvider):
    """Binds CacheManager to the container and wires the Cache facade."""

    def register(self) -> None:
        from arvel.cache import CacheManager
        from arvel.config.cache_config import CacheConfig
        from arvel.facades.cache import Cache

        c = self.app.container
        config = c.make(CacheConfig) if c.bound(CacheConfig) else CacheConfig()
        c.instance(CacheConfig, config)
        manager = CacheManager(config)
        c.instance(CacheManager, manager)
        Cache.bind(self.app.container)

    async def boot(self) -> None:
        from arvel.cache import migrations as cache_migrations

        stub = Path(cache_migrations.__file__).parent / "create_cache_table.py"
        self.publishes(
            {stub: "database/migrations"},
            tag="arvel-cache",
            is_migrations=True,
        )

    def commands(self) -> list[type[Command] | Command]:
        from arvel.console.commands.cache_commands import (
            CacheClearCommand,
            CacheForgetCommand,
        )

        return [CacheClearCommand, CacheForgetCommand]


__all__ = ["CacheServiceProvider"]
