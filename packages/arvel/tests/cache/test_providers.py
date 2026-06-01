"""Tests for ServiceProviders."""

from __future__ import annotations

import pytest
from arvel.application import Application
from arvel.providers.cache_provider import CacheServiceProvider
from arvel.providers.storage_provider import StorageServiceProvider


class TestCacheServiceProvider:
    def test_register_binds_cache_manager(self) -> None:
        from arvel.providers.cache_provider import CacheServiceProvider

        app = Application()
        provider = CacheServiceProvider(app)
        provider.register()

        from arvel.cache import CacheManager

        assert app.container.bound(CacheManager)

    def test_register_binds_cache_config(self) -> None:
        from arvel.config.cache_config import CacheConfig

        app = Application()
        provider = CacheServiceProvider(app)
        provider.register()
        assert app.container.bound(CacheConfig)

    @pytest.mark.asyncio
    async def test_boot_validates_store_config(self) -> None:
        app = Application()
        provider = CacheServiceProvider(app)
        provider.register()
        await provider.boot()

    def test_invalid_connection_raises_at_construction(self) -> None:
        from arvel.config.cache_config import CacheConfig
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            CacheConfig.model_validate({"connection": "nonexistent"})

    def test_commands_registered(self) -> None:
        app = Application()
        provider = CacheServiceProvider(app)
        commands = provider.commands()
        assert len(commands) >= 2


class TestStorageServiceProvider:
    @pytest.mark.asyncio
    async def test_boot_validates_default_disk(self) -> None:
        from arvel.config.storage_config import StorageConfig

        app = Application()
        config = StorageConfig(default="local")
        app.container.instance(StorageConfig, config)
        provider = StorageServiceProvider(app)
        provider.register()
        await provider.boot()

    def test_commands_include_storage_link(self) -> None:
        app = Application()
        provider = StorageServiceProvider(app)
        from arvel.console.commands.storage_link import StorageLinkCommand

        assert StorageLinkCommand in provider.commands()


class TestCacheFacadeAfterProviderRegister:
    """Cache facade usable after CacheServiceProvider.register()."""

    def test_cache_facade_get_works(self) -> None:
        from arvel.facades import Cache

        app = Application()
        provider = CacheServiceProvider(app)
        provider.register()
        assert Cache.manager is not None
