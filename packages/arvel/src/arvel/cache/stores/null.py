"""NullStore — discards all writes, always misses on reads."""

from __future__ import annotations

from typing import Any

from arvel.cache.exceptions import TagsNotSupported


class NullStore:
    """No-op cache store. Useful in tests to disable caching."""

    async def put(self, key: str, value: Any, ttl: int | None = None) -> None:
        pass

    async def get(self, key: str, default: Any = None) -> Any | None:
        return default

    async def forget(self, key: str) -> bool:
        return False

    async def has(self, key: str) -> bool:
        return False

    async def flush(self) -> None:
        pass

    async def forever(self, key: str, value: Any) -> None:
        pass

    async def many(self, keys: list[str]) -> dict[str, Any | None]:
        return dict.fromkeys(keys)

    async def put_many(self, values: dict[str, Any], ttl: int | None = None) -> None:
        pass

    def tags(self, tags: list[str]) -> None:
        raise TagsNotSupported("NullStore")


__all__ = ["NullStore"]
