"""NullCache — silently discards all writes, reads return default."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

from arvel.cache.contracts import CacheContract

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

T = TypeVar("T")


class NullCache(CacheContract):
    """No-op cache — writes are discarded, reads always miss."""

    async def get(self, key: str, default: T | None = None) -> T | None:
        return default

    async def put(self, key: str, value: Any, *, ttl: int | None = None) -> None:
        pass

    async def forget(self, key: str) -> bool:
        return False

    async def has(self, key: str) -> bool:
        return False

    async def flush(self) -> None:
        pass

    async def remember(
        self,
        key: str,
        ttl: int,
        callback: Callable[[], Awaitable[T]],
    ) -> T:
        return await callback()

    async def increment(self, key: str, value: int = 1) -> int:
        return value

    async def decrement(self, key: str, value: int = 1) -> int:
        return -value
