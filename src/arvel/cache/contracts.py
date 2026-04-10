"""Cache contract — ABC for swappable cache drivers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

T = TypeVar("T")


class CacheContract(ABC):
    """Abstract base class for cache drivers.

    Implementations: RedisCache (production), MemoryCache (testing/dev),
    NullCache (dry-run).
    """

    @abstractmethod
    async def get(self, key: str, default: T | None = None) -> T | None:
        """Return the cached value for *key*, or *default* if missing/expired."""

    @abstractmethod
    async def put(self, key: str, value: Any, *, ttl: int | None = None) -> None:
        """Store *value* under *key* with optional TTL in seconds.

        Raises CacheSerializationError if *value* is not JSON-serializable.
        """

    @abstractmethod
    async def forget(self, key: str) -> bool:
        """Remove *key* from the store. Return True if the key existed."""

    @abstractmethod
    async def has(self, key: str) -> bool:
        """Return True if *key* exists and hasn't expired."""

    @abstractmethod
    async def flush(self) -> None:
        """Remove all keys from the configured store."""

    @abstractmethod
    async def remember(
        self,
        key: str,
        ttl: int,
        callback: Callable[[], Awaitable[T]],
    ) -> T:
        """Return cached value for *key*; on miss, await *callback*, cache result, and return it."""

    @abstractmethod
    async def increment(self, key: str, value: int = 1) -> int:
        """Atomically increment an integer value. Return the new value."""

    @abstractmethod
    async def decrement(self, key: str, value: int = 1) -> int:
        """Atomically decrement an integer value. Return the new value."""
