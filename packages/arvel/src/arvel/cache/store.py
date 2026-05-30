"""CacheStore protocol — implemented by all cache backends."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class CacheStore(Protocol):
    """Async cache store interface.

    All implementations use duck typing — no inheritance required.
    TTL of None means "forever" (no expiry).
    """

    async def put(self, key: str, value: Any, ttl: int | None = None) -> None: ...
    async def get(self, key: str, default: Any = None) -> Any | None: ...
    async def forget(self, key: str) -> bool: ...
    # Presence is key-based. Cached None/False/0/"" still count as hits.
    async def has(self, key: str) -> bool: ...
    async def flush(self) -> None: ...
    async def forever(self, key: str, value: Any) -> None: ...
    async def many(self, keys: list[str]) -> dict[str, Any | None]: ...
    async def put_many(self, values: dict[str, Any], ttl: int | None = None) -> None: ...


__all__ = ["CacheStore"]
