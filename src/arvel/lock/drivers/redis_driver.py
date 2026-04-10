"""RedisLock — distributed locking via Redis SET NX."""

from __future__ import annotations

import uuid
from typing import Any

from arvel.lock.contracts import LockContract
from arvel.lock.exceptions import LockOwnershipError


class RedisLock(LockContract):
    """Distributed lock backed by Redis ``SET key value NX EX ttl``."""

    def __init__(self, client: Any) -> None:
        self._client = client

    async def acquire(
        self,
        key: str,
        ttl: int,
        *,
        owner: str | None = None,
        wait: bool = False,
    ) -> bool:
        actual_owner = owner or str(uuid.uuid4())
        result = await self._client.set(key, actual_owner, nx=True, ex=ttl)
        return bool(result)

    async def release(self, key: str, owner: str | None = None) -> bool:
        held_by = await self._client.get(key)
        if held_by is None:
            return False
        if isinstance(held_by, bytes):
            held_by = held_by.decode()
        if owner is not None and held_by != owner:
            raise LockOwnershipError(key, held_by, owner)
        await self._client.delete(key)
        return True

    async def extend(self, key: str, ttl: int) -> bool:
        return bool(await self._client.expire(key, ttl))

    async def is_locked(self, key: str) -> bool:
        return await self._client.exists(key) > 0

    async def aclose(self) -> None:
        close = getattr(self._client, "aclose", None)
        if callable(close):
            await close()
