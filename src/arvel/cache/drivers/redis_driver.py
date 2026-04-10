"""RedisCache — async Redis-backed cache with orjson serialization."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar, cast

import orjson

from arvel.cache.contracts import CacheContract
from arvel.cache.exceptions import CacheSerializationError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from typing import Protocol

    class _AsyncRedisClient(Protocol):
        """Minimal async Redis surface used by RedisCache."""

        async def get(self, name: str) -> bytes | None: ...

        async def set(
            self,
            name: str,
            value: bytes | str | int | float,
            *,
            ex: int | None = None,
        ) -> bool | None: ...

        async def delete(self, *names: str) -> int: ...

        async def exists(self, *keys: str) -> int: ...

        async def flushdb(self) -> None: ...

        async def incrby(self, name: str, amount: int) -> int: ...

        async def decrby(self, name: str, amount: int) -> int: ...


T = TypeVar("T")


class RedisCache(CacheContract):
    """Cache backed by an async Redis client."""

    def __init__(self, client: _AsyncRedisClient, prefix: str = "") -> None:
        self._client = client
        self._prefix = prefix

    def _prefixed(self, key: str) -> str:
        return f"{self._prefix}{key}"

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
        prefixed = self._prefixed(key)
        raw = await self._client.get(prefixed)
        if raw is None:
            return default
        return self._deserialize(raw)

    async def put(self, key: str, value: Any, *, ttl: int | None = None) -> None:
        prefixed = self._prefixed(key)
        payload = self._serialize(key, value)
        await self._client.set(prefixed, payload, ex=ttl)

    async def forget(self, key: str) -> bool:
        prefixed = self._prefixed(key)
        deleted = await self._client.delete(prefixed)
        return deleted > 0

    async def has(self, key: str) -> bool:
        prefixed = self._prefixed(key)
        count = await self._client.exists(prefixed)
        return count > 0

    async def flush(self) -> None:
        await self._client.flushdb()

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
        prefixed = self._prefixed(key)
        return await self._client.incrby(prefixed, value)

    async def decrement(self, key: str, value: int = 1) -> int:
        prefixed = self._prefixed(key)
        return await self._client.decrby(prefixed, value)

    async def aclose(self) -> None:
        close = getattr(self._client, "aclose", None)
        if callable(close):
            await close()
