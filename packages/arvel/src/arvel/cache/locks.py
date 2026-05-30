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

    async def block(self, timeout: float = 0) -> bool:
        """Poll until the lock is acquired or timeout elapses.

        Returns True if acquired, False on timeout.
        """
        deadline = time.monotonic() + timeout if timeout > 0 else float("inf")
        while True:
            acquired = await self.acquire()
            if acquired:
                return True
            if time.monotonic() >= deadline:
                return False
            await asyncio.sleep(0.05)

    async def __aenter__(self) -> bool:
        return await self.acquire()

    async def __aexit__(self, *args: object) -> None:
        await self.release()


__all__ = ["CacheLock"]
