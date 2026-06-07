"""CacheFakeContext + Cache.fake/.assert_* —"""

from __future__ import annotations

from types import TracebackType
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from arvel.cache import CacheManager


class CacheFakeContext:
    """Swap the bound CacheManager with an ARRAY-backed one for the duration of the test.

    Usage::

        with Cache.fake():
            await Cache.put("k", "v", ttl=60)
            Cache.assert_stored("k")
    """

    def __init__(self) -> None:
        self._original: CacheManager | None = None

    def __enter__(self) -> Self:
        from arvel.cache import CacheManager
        from arvel.config.cache_config import CacheConfig, CacheDriver
        from arvel.facades.cache import Cache

        self._original = Cache.manager
        # ARRAY driver is purely in-memory; file_path is unused by it but the
        # config object requires *some* value. Keep the default to avoid a
        # B108 false positive on a hardcoded /tmp path.
        cfg = CacheConfig(connection=CacheDriver.ARRAY, prefix="test:")
        Cache.manager = CacheManager(cfg)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        from arvel.facades.cache import Cache

        Cache.manager = self._original


__all__ = ["CacheFakeContext"]
