"""CacheLock — async context manager for distributed/local locks."""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import TYPE_CHECKING, Protocol, runtime_checkable
from weakref import WeakValueDictionary

if TYPE_CHECKING:
    from arvel.cache.store import CacheStore

# Per-key asyncio mutexes protect in-process stores (ArrayStore, FileStore,
# DatabaseStore) against the TOCTOU race in has() → put().
# WeakValue means the mutex is GC'd when no CacheLock instance holds a reference.
_process_mutexes: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()
_mutex_registry_lock = asyncio.Lock()


@runtime_checkable
class AtomicLockStore(Protocol):
    async def acquire_lock(self, key: str, owner: str, ttl: int) -> bool: ...
    async def release_lock(self, key: str, owner: str) -> bool: ...
    async def extend_lock(self, key: str, owner: str, ttl: int) -> bool: ...


def _get_or_create_mutex(key: str) -> asyncio.Lock:
    lock = _process_mutexes.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _process_mutexes[key] = lock
    return lock


class CacheLock:
    """Exclusive lock backed by any CacheStore.

    Usage::

        async with manager.lock("job:import", ttl=60) as acquired:
            if acquired:
                await do_work()
    """

    def __init__(self, store: CacheStore, name: str, ttl: int) -> None:
        self._store = store
        self._name = f"lock:{name}"
        self._ttl = ttl
        self._owner = uuid.uuid7().hex
        self._acquired = False

    async def acquire(self) -> bool:
        """Try to acquire the lock. Returns True if acquired, False otherwise."""
        if isinstance(self._store, AtomicLockStore):
            self._acquired = await self._store.acquire_lock(
                self._name,
                self._owner,
                self._ttl,
            )
            return self._acquired

        mutex = _get_or_create_mutex(self._name)
        async with mutex:
            if await self._store.has(self._name):
                return False
            await self._store.put(self._name, self._owner, ttl=self._ttl if self._ttl > 0 else None)
            self._acquired = True
            return True

    async def release(self) -> None:
        """Release the lock if we own it."""
        if isinstance(self._store, AtomicLockStore):
            await self._store.release_lock(self._name, self._owner)
            self._acquired = False
            return

        current = await self._store.get(self._name)
        if current == self._owner:
            await self._store.forget(self._name)
        self._acquired = False

    async def extend(self, ttl: int) -> bool:
        """Reset the lock's TTL to `ttl` seconds, only if we still own it.

        Returns False (without touching the lock) when a different owner holds
        it — long-running jobs use this to renew a lock they already acquired.
        """
        if isinstance(self._store, AtomicLockStore):
            return await self._store.extend_lock(self._name, self._owner, ttl)

        current = await self._store.get(self._name)
        if current != self._owner:
            return False
        await self._store.put(self._name, self._owner, ttl=ttl if ttl > 0 else None)
        return True

    async def block(
        self,
        timeout: float = 0,
        *,
        backoff: float = 0.05,
        max_backoff: float = 1.0,
    ) -> bool:
        """Poll until the lock is acquired or `timeout` elapses.

        Retry intervals grow exponentially from `backoff`, capped at
        `max_backoff`, to avoid hammering the store under contention.
        Returns True if acquired, False on timeout.
        """
        deadline = time.monotonic() + timeout if timeout > 0 else float("inf")
        delay = backoff
        while True:
            if await self.acquire():
                return True
            if time.monotonic() >= deadline:
                return False
            await asyncio.sleep(delay)
            delay = min(delay * 2, max_backoff)

    async def __aenter__(self) -> bool:
        return await self.acquire()

    async def __aexit__(self, *args: object) -> None:
        await self.release()


__all__ = ["CacheLock"]
