"""Typed cache configuration (``CACHE_*`` env vars)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, SecretStr
from pydantic_settings import SettingsConfigDict

from arvel.config.settings import ArvelSettings


class CacheDriver(StrEnum):
    ARRAY = "array"
    NULL = "null"
    FILE = "file"
    REDIS = "redis"
    DATABASE = "database"


class CacheConfig(ArvelSettings):
    """Cache subsystem settings.

    Two sources, in priority order:

    1. ``CACHE_URL`` — full Redis URL (e.g. ``redis://host:6379/0``). Wins when set.
    2. ``CACHE_CONNECTION`` + fine-grained ``CACHE_*``:

       - ``CACHE_CONNECTION``  driver name: ``redis``, ``file``, ``array``, ``database``, ``null``
       - ``CACHE_HOST``        Redis host (default: ``localhost``)
       - ``CACHE_PORT``        Redis port (default: 6379)
       - ``CACHE_PASSWORD``    Redis password (default: empty)
       - ``CACHE_DATABASE``    Redis DB index (default: 0)
       - ``CACHE_PREFIX``      key prefix (default: ``arvel_cache``)
       - ``CACHE_TTL``         default TTL in seconds (default: 3600)
       - ``CACHE_FILE_PATH``   path for file store (default: ``storage/framework/cache``)
       - ``CACHE_GC_PROBABILITY`` file store GC % (default: 2)

    When neither ``CACHE_URL`` nor ``CACHE_CONNECTION`` is set,
    ``enabled`` is ``False`` and the manager defaults to the ``array``
    store (safe in-process default, no external connection needed).

    Redis has no async driver suffix like SQLAlchemy. The ``redis.asyncio``
    package handles async natively — specify ``CACHE_CONNECTION=redis`` and
    the manager uses ``redis.asyncio.Redis`` (or ``from_url`` when
    ``CACHE_URL`` is set).

    ``array`` cache is fully supported: an in-process dict store with
    optional TTL. Useful in tests and single-process dev environments.
    """

    model_config = SettingsConfigDict(env_prefix="CACHE_", extra="ignore")

    # Full Redis URL — reads CACHE_URL.
    url: str | None = None
    # Driver name — reads CACHE_CONNECTION.
    connection: CacheDriver | None = None
    # Redis connection params.
    host: str = "localhost"
    port: int = 6379
    password: SecretStr = Field(default=SecretStr(""))
    database: int = 0
    # General options.
    prefix: str = "arvel_cache"
    ttl: int = 3600
    # File store options.
    file_path: str = "storage/framework/cache"
    gc_probability: int = 2

    @property
    def enabled(self) -> bool:
        """True when cache is explicitly configured via env."""
        return bool(self.url or self.connection is not None)

    @property
    def driver(self) -> CacheDriver:
        """Resolve the active driver.

        Defaults to ``array`` when neither ``CACHE_URL`` nor
        ``CACHE_CONNECTION`` is set, so local dev works without Redis.
        """
        return self.connection if self.connection is not None else CacheDriver.ARRAY


__all__ = ["CacheConfig", "CacheDriver"]
