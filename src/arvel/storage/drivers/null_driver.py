"""NullStorage — silently discards all writes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.storage.contracts import StorageContract

if TYPE_CHECKING:
    import builtins
    from datetime import timedelta


class NullStorage(StorageContract):
    """No-op storage — writes are discarded, reads always fail."""

    async def put(self, path: str, data: bytes, *, content_type: str | None = None) -> None:
        pass

    async def get(self, path: str) -> bytes:
        raise FileNotFoundError(f"File not found: {path}")

    async def delete(self, path: str) -> bool:
        return False

    async def exists(self, path: str) -> bool:
        return False

    async def url(self, path: str) -> str:
        return ""

    async def temporary_url(self, path: str, expiration: timedelta) -> str:
        return ""

    async def size(self, path: str) -> int:
        raise FileNotFoundError(f"File not found: {path}")

    async def list(self, prefix: str = "") -> builtins.list[str]:
        return []
