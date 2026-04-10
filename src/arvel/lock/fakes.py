"""LockFake — testing double that captures lock operations for assertion."""

from __future__ import annotations

from arvel.lock.drivers.memory_driver import MemoryLock


class LockFake(MemoryLock):
    """Extends MemoryLock with assertion helpers for tests."""

    def __init__(self) -> None:
        super().__init__()
        self._acquired_keys: list[str] = []

    async def acquire(
        self, key: str, ttl: int, *, owner: str | None = None, wait: bool = False
    ) -> bool:
        result = await super().acquire(key, ttl, owner=owner, wait=wait)
        if result:
            self._acquired_keys.append(key)
        return result

    def assert_acquired(self, key: str) -> None:
        if key not in self._acquired_keys:
            msg = f"Expected lock on '{key}' to be acquired, but it wasn't"
            raise AssertionError(msg)

    def assert_nothing_acquired(self) -> None:
        if self._acquired_keys:
            msg = f"Expected no locks acquired, but got: {self._acquired_keys}"
            raise AssertionError(msg)
