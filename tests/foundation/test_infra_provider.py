"""Tests for InfrastructureProvider — FB-S2-003.

The InfrastructureProvider reads config settings and registers the correct
driver implementation for each infrastructure contract.
"""

from __future__ import annotations

import pytest

from arvel.cache.contracts import CacheContract
from arvel.foundation.container import ContainerBuilder
from arvel.lock.contracts import LockContract
from arvel.mail.contracts import MailContract
from arvel.storage.contracts import StorageContract


class TestInfrastructureProvider:
    """FB-S2-003: InfrastructureProvider wires contracts to drivers by config."""

    def test_provider_is_service_provider(self) -> None:
        from arvel.foundation.provider import ServiceProvider
        from arvel.infra.provider import InfrastructureProvider

        assert issubclass(InfrastructureProvider, ServiceProvider)

    async def test_registers_cache_binding(self) -> None:
        from arvel.infra.provider import InfrastructureProvider

        builder = ContainerBuilder()
        provider = InfrastructureProvider()
        await provider.register(builder)
        container = builder.build()
        cache = await container.resolve(CacheContract)
        assert isinstance(cache, CacheContract)

    async def test_default_cache_driver_is_memory(self, clean_env: None) -> None:
        from arvel.cache.drivers.memory_driver import MemoryCache
        from arvel.infra.provider import InfrastructureProvider

        builder = ContainerBuilder()
        provider = InfrastructureProvider()
        await provider.register(builder)
        container = builder.build()
        cache = await container.resolve(CacheContract)
        assert isinstance(cache, MemoryCache)

    async def test_registers_mail_binding(self) -> None:
        from arvel.infra.provider import InfrastructureProvider

        builder = ContainerBuilder()
        provider = InfrastructureProvider()
        await provider.register(builder)
        container = builder.build()
        mail = await container.resolve(MailContract)
        assert isinstance(mail, MailContract)

    async def test_default_mail_driver_is_log(self, clean_env: None) -> None:
        from arvel.infra.provider import InfrastructureProvider
        from arvel.mail.drivers.log_driver import LogMailer

        builder = ContainerBuilder()
        provider = InfrastructureProvider()
        await provider.register(builder)
        container = builder.build()
        mail = await container.resolve(MailContract)
        assert isinstance(mail, LogMailer)

    async def test_registers_storage_binding(self) -> None:
        from arvel.infra.provider import InfrastructureProvider

        builder = ContainerBuilder()
        provider = InfrastructureProvider()
        await provider.register(builder)
        container = builder.build()
        storage = await container.resolve(StorageContract)
        assert isinstance(storage, StorageContract)

    async def test_default_storage_driver_is_local(self, clean_env: None) -> None:
        from arvel.infra.provider import InfrastructureProvider
        from arvel.storage.drivers.local_driver import LocalStorage

        builder = ContainerBuilder()
        provider = InfrastructureProvider()
        await provider.register(builder)
        container = builder.build()
        storage = await container.resolve(StorageContract)
        assert isinstance(storage, LocalStorage)

    async def test_registers_lock_binding(self) -> None:
        from arvel.infra.provider import InfrastructureProvider

        builder = ContainerBuilder()
        provider = InfrastructureProvider()
        await provider.register(builder)
        container = builder.build()
        lock = await container.resolve(LockContract)
        assert isinstance(lock, LockContract)

    async def test_default_lock_driver_is_memory(self, clean_env: None) -> None:
        from arvel.infra.provider import InfrastructureProvider
        from arvel.lock.drivers.memory_driver import MemoryLock

        builder = ContainerBuilder()
        provider = InfrastructureProvider()
        await provider.register(builder)
        container = builder.build()
        lock = await container.resolve(LockContract)
        assert isinstance(lock, MemoryLock)

    async def test_provider_priority_is_framework_level(self) -> None:
        from arvel.infra.provider import InfrastructureProvider

        provider = InfrastructureProvider()
        assert provider.priority <= 20

    async def test_cache_driver_redis_when_available(self, monkeypatch, clean_env: None) -> None:
        pytest.importorskip("redis.asyncio")
        from arvel.cache.drivers.redis_driver import RedisCache
        from arvel.infra.provider import InfrastructureProvider

        monkeypatch.setenv("CACHE_DRIVER", "redis")

        builder = ContainerBuilder()
        provider = InfrastructureProvider()
        await provider.register(builder)
        container = builder.build()
        cache = await container.resolve(CacheContract)
        assert isinstance(cache, RedisCache)

    async def test_mail_driver_smtp_when_available(self, monkeypatch, clean_env: None) -> None:
        pytest.importorskip("aiosmtplib")
        from arvel.infra.provider import InfrastructureProvider
        from arvel.mail.drivers.smtp_driver import SmtpMailer

        monkeypatch.setenv("MAIL_DRIVER", "smtp")

        builder = ContainerBuilder()
        provider = InfrastructureProvider()
        await provider.register(builder)
        container = builder.build()
        mailer = await container.resolve(MailContract)
        assert isinstance(mailer, SmtpMailer)

    async def test_storage_driver_s3_when_available(self, monkeypatch, clean_env: None) -> None:
        pytest.importorskip("aiobotocore.session")
        from arvel.infra.provider import InfrastructureProvider
        from arvel.storage.drivers.managed_s3_driver import ManagedS3Storage

        monkeypatch.setenv("STORAGE_DRIVER", "s3")
        monkeypatch.setenv("STORAGE_S3_BUCKET", "test-bucket")

        builder = ContainerBuilder()
        provider = InfrastructureProvider()
        await provider.register(builder)
        container = builder.build()
        storage = await container.resolve(StorageContract)
        assert isinstance(storage, ManagedS3Storage)

    async def test_lock_driver_redis_when_available(self, monkeypatch, clean_env: None) -> None:
        pytest.importorskip("redis.asyncio")
        from arvel.infra.provider import InfrastructureProvider
        from arvel.lock.drivers.redis_driver import RedisLock

        monkeypatch.setenv("LOCK_DRIVER", "redis")

        builder = ContainerBuilder()
        provider = InfrastructureProvider()
        await provider.register(builder)
        container = builder.build()
        lock = await container.resolve(LockContract)
        assert isinstance(lock, RedisLock)
