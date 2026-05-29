"""ArrayStore — in-process dict-backed cache with per-key expiry."""

from __future__ import annotations

import time
from typing import Any, NamedTuple


class _Entry(NamedTuple):
    value: Any
    expires_at: float  # monotonic; 0.0 means "forever"


class ArrayStore:
    """In-process cache using a plain dict. TTL is enforced via monotonic timestamps.

    Thread-safe for the cooperative asyncio case; not safe for multi-threaded use.
    """

    def __init__(self, prefix: str = "arvel_cache") -> None:
        self._prefix = prefix
        self.entries: dict[str, _Entry] = {}

    def _full_key(self, key: str) -> str:
        return f"{self._prefix}:{key}"

    def _is_expired(self, entry: _Entry) -> bool:
        return entry.expires_at != 0.0 and time.monotonic() > entry.expires_at

    async def put(self, key: str, value: Any, ttl: int | None = None) -> None:
        expires_at = 0.0 if ttl is None else time.monotonic() + ttl
        self.entries[self._full_key(key)] = _Entry(value=value, expires_at=expires_at)

    async def get(self, key: str, default: Any = None) -> Any | None:
        entry = self.entries.get(self._full_key(key))
        if entry is None or self._is_expired(entry):
            if entry is not None:
                del self.entries[self._full_key(key)]
            return default
        return entry.value

    async def forget(self, key: str) -> bool:
        return self.entries.pop(self._full_key(key), None) is not None

    async def has(self, key: str) -> bool:
        entry = self.entries.get(self._full_key(key))
        if entry is None:
            return False
        if self._is_expired(entry):
            del self.entries[self._full_key(key)]
            return False
        return True

    async def flush(self) -> None:
        self.entries.clear()

    async def forever(self, key: str, value: Any) -> None:
        await self.put(key, value, ttl=None)

    async def many(self, keys: list[str]) -> dict[str, Any | None]:
        return {k: await self.get(k) for k in keys}

    async def put_many(self, values: dict[str, Any], ttl: int | None = None) -> None:
        for k, v in values.items():
            await self.put(k, v, ttl=ttl)

    async def gc(self, max_lifetime: int = 0) -> int:
        now = time.monotonic()
        stale = [k for k, v in self.entries.items() if v.expires_at != 0.0 and now > v.expires_at]
        for k in stale:
            del self.entries[k]
        return len(stale)


__all__ = ["ArrayStore"]
