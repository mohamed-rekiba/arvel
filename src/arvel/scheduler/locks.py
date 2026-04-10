"""Lock backends for scheduler overlap prevention."""

from __future__ import annotations

import time
from typing import Protocol, runtime_checkable


@runtime_checkable
class LockBackend(Protocol):
    """Protocol for scheduler overlap prevention locks."""

    async def acquire(self, key: str, ttl: int) -> bool: ...
    async def release(self, key: str) -> None: ...
    async def is_locked(self, key: str) -> bool: ...


class InMemoryLockBackend:
    """In-memory lock for single-process / testing use.

    Locks expire based on TTL (seconds from acquisition time).
    """

    def __init__(self) -> None:
        self._locks: dict[str, float] = {}

    async def acquire(self, key: str, ttl: int) -> bool:
        if key in self._locks:
            if time.monotonic() < self._locks[key]:
                return False
            del self._locks[key]
        self._locks[key] = time.monotonic() + ttl
        return True

    async def release(self, key: str) -> None:
        self._locks.pop(key, None)

    async def is_locked(self, key: str) -> bool:
        if key not in self._locks:
            return False
        if time.monotonic() >= self._locks[key]:
            del self._locks[key]
            return False
        return True


class NullLockBackend:
    """No-op lock — overlap prevention disabled."""

    async def acquire(self, key: str, ttl: int) -> bool:
        return True

    async def release(self, key: str) -> None:
        pass

    async def is_locked(self, key: str) -> bool:
        return False
