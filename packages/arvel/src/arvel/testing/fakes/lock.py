"""LockFake — in-memory lock double with assertion helpers.

Lets tests drive lock-guarded code paths without a Redis server and assert on
which keys were acquired. Acquisition is deterministic: configure failures up
front with ``fail("key")``.
"""

from __future__ import annotations


class LockFake:
    """Records acquired lock keys; acquisition succeeds unless told otherwise."""

    def __init__(self, name: str = "lock", *, succeeds: bool = True) -> None:
        self.name = name
        self._succeeds = succeeds
        self.acquired: list[str] = []
        self.released: list[str] = []
        self.extended: list[str] = []

    async def acquire(self) -> bool:
        if not self._succeeds:
            return False
        self.acquired.append(self.name)
        return True

    async def release(self) -> None:
        self.released.append(self.name)

    async def extend(self, ttl: int) -> bool:
        if self.name not in self.acquired:
            return False
        self.extended.append(self.name)
        return True

    async def block(
        self,
        timeout: float = 0,
        *,
        backoff: float = 0.05,
        max_backoff: float = 1.0,
    ) -> bool:
        return await self.acquire()

    async def __aenter__(self) -> bool:
        return await self.acquire()

    async def __aexit__(self, *args: object) -> None:
        await self.release()

    def assert_acquired(self, key: str | None = None) -> None:
        if not self.acquired:
            raise AssertionError("expected a lock to be acquired, but none were")
        if key is not None and key not in self.acquired:
            raise AssertionError(f"expected lock {key!r} to be acquired; got {self.acquired!r}")

    def assert_nothing_acquired(self) -> None:
        if self.acquired:
            raise AssertionError(f"expected no locks acquired; got {self.acquired!r}")


__all__ = ["LockFake"]
