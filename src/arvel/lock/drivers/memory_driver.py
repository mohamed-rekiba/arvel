"""MemoryLock — in-process locking with TTL and ownership."""

from __future__ import annotations

import time
import uuid

from arvel.lock.contracts import LockContract
from arvel.lock.exceptions import LockOwnershipError


class MemoryLock(LockContract):
    """In-process lock backed by a Python dict with monotonic-clock TTL."""

    def __init__(self) -> None:
        self._locks: dict[str, tuple[str, float]] = {}

    def _is_expired(self, key: str) -> bool:
        entry = self._locks.get(key)
        if entry is None:
            return True
        _, expires_at = entry
        return time.monotonic() >= expires_at

    def _cleanup(self, key: str) -> None:
        if self._is_expired(key):
            self._locks.pop(key, None)

    async def acquire(
        self,
        key: str,
        ttl: int,
        *,
        owner: str | None = None,
        wait: bool = False,
    ) -> bool:
        self._cleanup(key)
        if key in self._locks:
            return False
        actual_owner = owner or str(uuid.uuid4())
        self._locks[key] = (actual_owner, time.monotonic() + ttl)
        return True

    async def release(self, key: str, owner: str | None = None) -> bool:
        self._cleanup(key)
        entry = self._locks.get(key)
        if entry is None:
            return False
        held_by, _ = entry
        if owner is not None and held_by != owner:
            raise LockOwnershipError(key, held_by, owner)
        del self._locks[key]
        return True

    async def extend(self, key: str, ttl: int) -> bool:
        self._cleanup(key)
        entry = self._locks.get(key)
        if entry is None:
            return False
        held_by, _ = entry
        self._locks[key] = (held_by, time.monotonic() + ttl)
        return True

    async def is_locked(self, key: str) -> bool:
        self._cleanup(key)
        return key in self._locks
