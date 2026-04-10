"""MemoryCache — in-process dict with TTL expiry."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, TypeVar, cast

import orjson

from arvel.cache.contracts import CacheContract
from arvel.cache.exceptions import CacheSerializationError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

T = TypeVar("T")


class MemoryCache(CacheContract):
    """In-process cache backed by a Python dict with monotonic-clock TTL."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[bytes, float | None]] = {}

    def _is_expired(self, expires_at: float | None) -> bool:
        if expires_at is None:
            return False
        return time.monotonic() >= expires_at

    def _serialize(self, key: str, value: Any) -> bytes:
        try:
            return orjson.dumps(value)
        except TypeError as exc:
            raise CacheSerializationError(
                key,
                type(value).__name__,
                str(exc),
            ) from exc

    def _deserialize(self, raw: bytes) -> Any:
        return orjson.loads(raw)

    async def get(self, key: str, default: T | None = None) -> T | None:
        entry = self._store.get(key)
        if entry is None:
            return default
        raw, expires_at = entry
        if self._is_expired(expires_at):
            del self._store[key]
            return default
        return self._deserialize(raw)

    async def put(self, key: str, value: Any, *, ttl: int | None = None) -> None:
        raw = self._serialize(key, value)
        expires_at = (time.monotonic() + ttl) if ttl is not None else None
        self._store[key] = (raw, expires_at)

    async def forget(self, key: str) -> bool:
        entry = self._store.pop(key, None)
        return entry is not None

    async def has(self, key: str) -> bool:
        entry = self._store.get(key)
        if entry is None:
            return False
        _, expires_at = entry
        if self._is_expired(expires_at):
            del self._store[key]
            return False
        return True

    async def flush(self) -> None:
        self._store.clear()

    async def remember(
        self,
        key: str,
        ttl: int,
        callback: Callable[[], Awaitable[T]],
    ) -> T:
        existing = await self.get(key)
        if existing is not None:
            return cast("T", existing)
        result = await callback()
        await self.put(key, result, ttl=ttl)
        return result

    async def increment(self, key: str, value: int = 1) -> int:
        current = await self.get(key, default=0)
        new_val = int(current if current is not None else 0) + value
        await self.put(key, new_val)
        return new_val

    async def decrement(self, key: str, value: int = 1) -> int:
        return await self.increment(key, -value)
