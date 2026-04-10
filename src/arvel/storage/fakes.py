"""StorageFake — in-memory testing double that captures operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.storage.contracts import StorageContract

if TYPE_CHECKING:
    import builtins
    from datetime import timedelta


class StorageFake(StorageContract):
    """In-memory storage for tests with assertion helpers."""

    def __init__(self) -> None:
        self._files: dict[str, bytes] = {}

    async def put(self, path: str, data: bytes, *, content_type: str | None = None) -> None:
        self._files[path] = data

    async def get(self, path: str) -> bytes:
        if path not in self._files:
            raise FileNotFoundError(f"File not found: {path}")
        return self._files[path]

    async def delete(self, path: str) -> bool:
        return self._files.pop(path, None) is not None

    async def exists(self, path: str) -> bool:
        return path in self._files

    async def url(self, path: str) -> str:
        return f"/fake-storage/{path}"

    async def temporary_url(self, path: str, expiration: timedelta) -> str:
        return f"/fake-storage/{path}?expires={int(expiration.total_seconds())}"

    async def size(self, path: str) -> int:
        if path not in self._files:
            raise FileNotFoundError(f"File not found: {path}")
        return len(self._files[path])

    async def list(self, prefix: str = "") -> builtins.list[str]:
        return sorted(k for k in self._files if k.startswith(prefix))

    def assert_stored(self, path: str) -> None:
        if path not in self._files:
            msg = f"Expected file at '{path}' to be stored, but it wasn't"
            raise AssertionError(msg)

    def assert_not_stored(self, path: str) -> None:
        if path in self._files:
            msg = f"Expected file at '{path}' not to be stored, but it was"
            raise AssertionError(msg)

    def assert_nothing_stored(self) -> None:
        if self._files:
            keys = list(self._files.keys())
            msg = f"Expected no files stored, but got {len(self._files)}: {keys}"
            raise AssertionError(msg)
