"""NullLock — always succeeds (no-op locking)."""

from __future__ import annotations

from arvel.lock.contracts import LockContract


class NullLock(LockContract):
    """No-op lock — acquire always succeeds, is_locked always returns False."""

    async def acquire(
        self,
        key: str,
        ttl: int,
        *,
        owner: str | None = None,
        wait: bool = False,
    ) -> bool:
        return True

    async def release(self, key: str, owner: str | None = None) -> bool:
        return True

    async def extend(self, key: str, ttl: int) -> bool:
        return True

    async def is_locked(self, key: str) -> bool:
        return False
