"""InfrastructureProvider — wires infrastructure contracts to drivers by config."""

from __future__ import annotations

import contextlib
import inspect
from typing import TYPE_CHECKING, Any, cast

from arvel.cache.config import CacheSettings
from arvel.cache.contracts import CacheContract
from arvel.foundation.config import get_module_settings
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
    from arvel.app.config import AppSettings
    from arvel.foundation.application import Application
    from arvel.foundation.container import ContainerBuilder

logger = Log.named("arvel.infra.provider")


class InfrastructureProvider(ServiceProvider):
    """Cache, mail, storage, lock — picks drivers from config."""

    priority = 10

    _cache_settings: CacheSettings | None
    _mail_settings: MailSettings | None
    _storage_settings: StorageSettings | None
    _lock_settings: LockSettings | None

    def __init__(self) -> None:
        super().__init__()
        self._cache_settings = None
        self._mail_settings = None
        self._storage_settings = None
        self._lock_settings = None

    def configure(self, config: AppSettings) -> None:
        for settings_type, attr in (
            (CacheSettings, "_cache_settings"),
            (MailSettings, "_mail_settings"),
            (StorageSettings, "_storage_settings"),
            (LockSettings, "_lock_settings"),
        ):
            with contextlib.suppress(Exception):
                setattr(self, attr, get_module_settings(config, settings_type))

    def _get_cache_settings(self) -> CacheSettings:
        if self._cache_settings is not None:
            return self._cache_settings
        return CacheSettings()

    def _get_mail_settings(self) -> MailSettings:
        if self._mail_settings is not None:
            return self._mail_settings
        return MailSettings()

    def _get_storage_settings(self) -> StorageSettings:
        if self._storage_settings is not None:
            return self._storage_settings
        return StorageSettings()

    def _get_lock_settings(self) -> LockSettings:
        if self._lock_settings is not None:
            return self._lock_settings
        return LockSettings()

    def _make_cache(self) -> CacheContract:
        settings = self._get_cache_settings()
        if settings.driver == "null":
            from arvel.cache.drivers.null_driver import NullCache

            return NullCache()
        if settings.driver == "memory":
            from arvel.cache.drivers.memory_driver import MemoryCache

            return MemoryCache()
        if settings.driver == "redis":
            import redis.asyncio as aioredis

            from arvel.cache.drivers.redis_driver import RedisCache

            client = aioredis.from_url(settings.redis_url)
            return RedisCache(client=cast("Any", client), prefix=settings.prefix)
        raise ConfigurationError(f"Unsupported CACHE_DRIVER '{settings.driver}'")

    def _make_mail(self) -> MailContract:
        settings = self._get_mail_settings()
        if settings.driver == "null":
            from arvel.mail.drivers.null_driver import NullMailer

            return NullMailer()
        if settings.driver == "log":
            from arvel.mail.drivers.log_driver import LogMailer

            return LogMailer()
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

    def _make_storage(self) -> StorageContract:
        settings = self._get_storage_settings()
        if settings.driver == "null":
            from arvel.storage.drivers.null_driver import NullStorage

            return NullStorage()
        if settings.driver == "local":
            from arvel.storage.drivers.local_driver import LocalStorage

            return LocalStorage(root=settings.local_root, base_url=settings.local_base_url)
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

    def _make_lock(self) -> LockContract:
        settings = self._get_lock_settings()
        if settings.driver == "null":
            from arvel.lock.drivers.null_driver import NullLock

            return NullLock()
        if settings.driver == "memory":
            from arvel.lock.drivers.memory_driver import MemoryLock

            return MemoryLock()
        if settings.driver == "redis":
            import redis.asyncio as aioredis

            from arvel.lock.drivers.redis_driver import RedisLock

            client = aioredis.from_url(settings.redis_url)
            return RedisLock(client=client)
        raise ConfigurationError(f"Unsupported LOCK_DRIVER '{settings.driver}'")

    async def register(self, container: ContainerBuilder) -> None:
        container.provide_factory(CacheContract, self._make_cache, scope=Scope.APP)
        container.provide_factory(MailContract, self._make_mail, scope=Scope.APP)
        container.provide_factory(StorageContract, self._make_storage, scope=Scope.APP)
        container.provide_factory(LockContract, self._make_lock, scope=Scope.APP)

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
