"""Rate-limit store abstraction + drivers."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class Attempt:
    """Result of a single ``store.hit(...)`` call."""

    count: int
    reset_at: datetime


@runtime_checkable
class RateLimiterStore(Protocol):
    """Pluggable backend for the ``Throttle`` middleware."""

    async def hit(self, key: str, *, decay_seconds: int) -> Attempt: ...


class InMemoryStore:
    """Process-local store. Fine for dev, tests, single-process apps."""

    def __init__(self) -> None:
        self._windows: dict[str, tuple[int, float]] = {}
        self._lock = asyncio.Lock()

    async def hit(self, key: str, *, decay_seconds: int) -> Attempt:
        now = time.monotonic()
        async with self._lock:
            count, expires_at = self._windows.get(key, (0, 0.0))
            if decay_seconds <= 0 or now >= expires_at:
                count = 1
                expires_at = now + max(decay_seconds, 0)
            else:
                count += 1
            self._windows[key] = (count, expires_at)
        reset_at = datetime.fromtimestamp(time.time() + max(expires_at - now, 0), tz=UTC)
        return Attempt(count=count, reset_at=reset_at)


class RedisStore:
    """Redis-backed store for multi-process deployments.

    Imports redis lazily so the dependency is only required when this store is
    actually instantiated (``arvel[redis]`` extra).
    """

    def __init__(self, client: object, *, key_prefix: str = "arvel:rl:") -> None:
        self._client = client
        self._key_prefix = key_prefix

    @staticmethod
    def _hash_key(key: str) -> str:
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    async def hit(self, key: str, *, decay_seconds: int) -> Attempt:
        scoped = f"{self._key_prefix}{self._hash_key(key)}"
        incr = getattr(self._client, "incr", None)
        expire = getattr(self._client, "expire", None)
        if not callable(incr) or not callable(expire):
            msg = "redis client must expose incr/expire (sync or async)"
            raise TypeError(msg)
        count = int(await _await_if_needed(incr(scoped)))
        if count == 1 and decay_seconds > 0:
            await _await_if_needed(expire(scoped, decay_seconds))
        reset_at = datetime.fromtimestamp(time.time() + max(decay_seconds, 0), tz=UTC)
        return Attempt(count=count, reset_at=reset_at)


async def _await_if_needed(value: Any) -> Any:
    """Await ``value`` if it is awaitable; otherwise return it as-is."""
    if inspect.isawaitable(value):
        return await value
    return value


__all__ = [
    "Attempt",
    "InMemoryStore",
    "RateLimiterStore",
    "RedisStore",
]
