"""RedisStore — Redis-backed cache using redis.asyncio (optional dep: arvel[redis])."""

from __future__ import annotations

import json
from typing import Any, Protocol


class RedisConn(Protocol):
    """Minimal interface of redis.asyncio.Redis used by RedisStore."""

    async def set(self, name: str, value: str | bytes, **kwargs: Any) -> Any: ...
    async def setex(self, name: str, time: int, value: str | bytes) -> Any: ...
    async def get(self, name: str) -> bytes | None: ...
    async def delete(self, *names: str) -> int: ...
    async def eval(self, script: str, numkeys: int, *keys_and_args: str) -> int: ...
    async def exists(self, *names: str) -> int: ...
    async def keys(self, pattern: str) -> list[bytes]: ...
    async def mget(self, *keys: str) -> list[bytes | None]: ...
    async def scan(
        self, cursor: int, match: str | None = None, count: int | None = None
    ) -> tuple[int, list[bytes]]: ...


class RedisStore:
    """Cache store backed by Redis.

    Requires ``arvel[redis]``: ``pip install "arvel[redis]"``.
    """

    def __init__(self, redis: RedisConn, prefix: str, ttl: int = 3600) -> None:
        self._redis = redis
        self._prefix = prefix
        self._default_ttl = ttl

    def _key(self, key: str) -> str:
        return f"{self._prefix}:{key}"

    def _serialize(self, value: Any) -> str:
        return json.dumps(value)

    def _deserialize(self, raw: bytes) -> Any:
        return json.loads(raw.decode())

    async def put(self, key: str, value: Any, ttl: int | None = None) -> None:
        effective_ttl = ttl if ttl is not None else self._default_ttl
        serialized = self._serialize(value)
        if effective_ttl == 0:
            await self._redis.set(self._key(key), serialized)
        else:
            await self._redis.setex(self._key(key), effective_ttl, serialized)

    async def get(self, key: str, default: Any = None) -> Any | None:
        raw = await self._redis.get(self._key(key))
        if raw is None:
            return default
        return self._deserialize(raw)

    async def forget(self, key: str) -> bool:
        deleted = await self._redis.delete(self._key(key))
        return bool(deleted)

    async def has(self, key: str) -> bool:
        return bool(await self._redis.exists(self._key(key)))

    async def acquire_lock(self, key: str, owner: str, ttl: int) -> bool:
        options: dict[str, bool | int] = {"nx": True}
        if ttl > 0:
            options["ex"] = ttl
        return bool(await self._redis.set(self._key(key), owner, **options))

    async def release_lock(self, key: str, owner: str) -> bool:
        script = (
            'if redis.call("GET", KEYS[1]) == ARGV[1] then '
            'return redis.call("DEL", KEYS[1]) end return 0'
        )
        released = await self._redis.eval(script, 1, self._key(key), owner)
        return bool(released)

    async def extend_lock(self, key: str, owner: str, ttl: int) -> bool:
        # Owner check + EXPIRE are atomic so a non-owner can't renew the lock.
        script = (
            'if redis.call("GET", KEYS[1]) == ARGV[1] then '
            'return redis.call("EXPIRE", KEYS[1], ARGV[2]) end return 0'
        )
        # EXPIRE's seconds arg is passed as a string ARGV, like every redis-py eval arg.
        extended = await self._redis.eval(script, 1, self._key(key), owner, str(ttl))
        return bool(extended)

    async def flush(self) -> None:
        # KEYS blocks the Redis event loop; SCAN iterates non-blocking in batches.
        pattern = f"{self._prefix}:*"
        cursor: int = 0
        while True:
            cursor, batch = await self._redis.scan(cursor, match=pattern, count=100)
            if batch:
                keys_to_delete = [k.decode() for k in batch]
                await self._redis.delete(*keys_to_delete)
            if cursor == 0:
                break

    async def forever(self, key: str, value: Any) -> None:
        await self._redis.set(self._key(key), self._serialize(value))

    async def many(self, keys: list[str]) -> dict[str, Any | None]:
        rkeys = [self._key(k) for k in keys]
        raws = await self._redis.mget(*rkeys)
        return {
            k: (self._deserialize(raw) if raw is not None else None)
            for k, raw in zip(keys, raws, strict=True)
        }

    async def put_many(self, values: dict[str, Any], ttl: int | None = None) -> None:
        for k, v in values.items():
            await self.put(k, v, ttl=ttl)


__all__ = ["RedisConn", "RedisStore"]
