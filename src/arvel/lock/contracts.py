"""Lock contract — ABC for swappable distributed lock drivers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class LockContract(ABC):
    """Abstract base class for distributed lock drivers.

    Implementations: RedisLock (production), MemoryLock (testing/dev),
    NullLock (dry-run).
    """

    @abstractmethod
    async def acquire(
        self,
        key: str,
        ttl: int,
        *,
        owner: str | None = None,
        wait: bool = False,
    ) -> bool:
        """Acquire a lock on *key* for *ttl* seconds.

        Returns True on success. When *wait* is False and the lock is held,
        returns False immediately. When *wait* is True, blocks until the lock
        becomes available or TTL expires.

        *owner* identifies the lock holder (defaults to a generated UUID4).
        """

    @abstractmethod
    async def release(self, key: str, owner: str | None = None) -> bool:
        """Release the lock on *key*.

        When *owner* is provided, only releases if the current holder matches.
        Returns True if the lock was released.
        Raises LockOwnershipError if owner doesn't match.
        """

    @abstractmethod
    async def extend(self, key: str, ttl: int) -> bool:
        """Extend the TTL of an existing lock. Returns True if the lock existed."""

    @abstractmethod
    async def is_locked(self, key: str) -> bool:
        """Return True if *key* is currently locked."""

    @asynccontextmanager
    async def with_lock(
        self,
        key: str,
        ttl: int,
        *,
        owner: str | None = None,
    ) -> AsyncIterator[None]:
        """Async context manager that acquires on entry and releases on exit.

        Raises LockAcquisitionError if the lock cannot be acquired.
        """
        acquired = await self.acquire(key, ttl, owner=owner)
        if not acquired:
            from arvel.lock.exceptions import LockAcquisitionError

            raise LockAcquisitionError(key)
        try:
            yield
        finally:
            await self.release(key, owner=owner)
