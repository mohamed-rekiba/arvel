"""InfrastructureProvider — wires infrastructure contracts to drivers by config."""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any, cast

from arvel.cache.config import CacheSettings
from arvel.cache.contracts import CacheContract
from arvel.foundation.container import Scope
from arvel.foundation.exceptions import ConfigurationError
from arvel.foundation.provider import ServiceProvider
from arvel.lock.config import LockSettings
from arvel.lock.contracts import LockContract
from arvel.logging import Log
from arvel.mail.config import MailSettings
from arvel.mail.contracts import MailContract
from arvel.storage.config import StorageSettings
from arvel.storage.contracts import StorageContract

if TYPE_CHECKING:
    from arvel.foundation.application import Application
    from arvel.foundation.container import ContainerBuilder

logger = Log.named("arvel.infra.provider")


def _make_cache() -> CacheContract:
    settings = CacheSettings()
    if settings.driver == "null":
        from arvel.cache.drivers.null_driver import NullCache

        return NullCache()
    if settings.driver == "memory":
        return _default_cache()
    if settings.driver == "redis":
        import redis.asyncio as aioredis

        from arvel.cache.drivers.redis_driver import RedisCache

        client = aioredis.from_url(settings.redis_url)
        return RedisCache(client=cast("Any", client), prefix=settings.prefix)
    raise ConfigurationError(f"Unsupported CACHE_DRIVER '{settings.driver}'")


def _default_cache() -> CacheContract:
    from arvel.cache.drivers.memory_driver import MemoryCache

    return MemoryCache()


def _make_mail() -> MailContract:
    settings = MailSettings()
    if settings.driver == "null":
        from arvel.mail.drivers.null_driver import NullMailer

        return NullMailer()
    if settings.driver == "log":
        return _default_mail()
    if settings.driver == "smtp":
        from arvel.mail.drivers.smtp_driver import SmtpMailer

        return SmtpMailer(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password.get_secret_value(),
            use_tls=settings.smtp_use_tls,
            from_address=settings.from_address,
            from_name=settings.from_name,
            template_dir=settings.template_dir,
        )
    raise ConfigurationError(f"Unsupported MAIL_DRIVER '{settings.driver}'")


def _default_mail() -> MailContract:
    from arvel.mail.drivers.log_driver import LogMailer

    return LogMailer()


def _make_storage() -> StorageContract:
    settings = StorageSettings()
    if settings.driver == "null":
        from arvel.storage.drivers.null_driver import NullStorage

        return NullStorage()
    if settings.driver == "local":
        return _default_storage()
    if settings.driver == "s3":
        from arvel.storage.drivers.managed_s3_driver import ManagedS3Storage

        return ManagedS3Storage(
            bucket=settings.s3_bucket,
            region=settings.s3_region,
            endpoint_url=settings.s3_endpoint_url,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key.get_secret_value(),
        )
    raise ConfigurationError(f"Unsupported STORAGE_DRIVER '{settings.driver}'")


def _default_storage() -> StorageContract:
    from arvel.storage.drivers.local_driver import LocalStorage

    settings = StorageSettings()
    return LocalStorage(root=settings.local_root, base_url=settings.local_base_url)


def _make_lock() -> LockContract:
    settings = LockSettings()
    if settings.driver == "null":
        from arvel.lock.drivers.null_driver import NullLock

        return NullLock()
    if settings.driver == "memory":
        return _default_lock()
    if settings.driver == "redis":
        import redis.asyncio as aioredis

        from arvel.lock.drivers.redis_driver import RedisLock

        client = aioredis.from_url(settings.redis_url)
        return RedisLock(client=client)
    raise ConfigurationError(f"Unsupported LOCK_DRIVER '{settings.driver}'")


def _default_lock() -> LockContract:
    from arvel.lock.drivers.memory_driver import MemoryLock

    return MemoryLock()


class InfrastructureProvider(ServiceProvider):
    """Registers infrastructure contracts with their default drivers.

    Reads each contract's settings to decide which driver to wire.
    Defaults: MemoryCache, LogMailer, LocalStorage, MemoryLock.
    """

    priority = 10

    async def register(self, container: ContainerBuilder) -> None:
        container.provide_factory(CacheContract, _make_cache, scope=Scope.APP)
        container.provide_factory(MailContract, _make_mail, scope=Scope.APP)
        container.provide_factory(StorageContract, _make_storage, scope=Scope.APP)
        container.provide_factory(LockContract, _make_lock, scope=Scope.APP)

    async def shutdown(self, app: Application) -> None:
        for contract in (CacheContract, StorageContract, LockContract):
            try:
                resource = await app.container.resolve(contract)
            except Exception as exc:
                logger.warning(
                    "infra_shutdown_resolve_failed",
                    contract=contract.__name__,
                    error=type(exc).__name__,
                )
                continue

            close_fn = getattr(resource, "aclose", None)
            if callable(close_fn):
                result = close_fn()
                if inspect.isawaitable(result):
                    await result
                continue

            close_fn = getattr(resource, "close", None)
            if callable(close_fn):
                result = close_fn()
                if inspect.isawaitable(result):
                    await result

        logger.info("infra_shutdown_complete")
