"""CacheFake — testing double that captures operations for assertion."""

from __future__ import annotations

from typing import Any

from arvel.cache.drivers.memory_driver import MemoryCache


class CacheFake(MemoryCache):
    """Extends MemoryCache with assertion helpers for tests."""

    def __init__(self) -> None:
        super().__init__()
        self._puts: list[str] = []

    async def put(self, key: str, value: Any, *, ttl: int | None = None) -> None:
        self._puts.append(key)
        await super().put(key, value, ttl=ttl)

    def assert_put(self, key: str) -> None:
        if key not in self._puts:
            msg = f"Expected cache put for '{key}', but it wasn't called"
            raise AssertionError(msg)

    def assert_not_put(self, key: str) -> None:
        if key in self._puts:
            msg = f"Expected '{key}' not to be put in cache, but it was"
            raise AssertionError(msg)

    def assert_nothing_put(self) -> None:
        if self._puts:
            msg = f"Expected no cache puts, but got {len(self._puts)}: {self._puts}"
            raise AssertionError(msg)
