"""In-memory storage driver — for testing and ephemeral workloads."""

from __future__ import annotations

from typing import BinaryIO

from arvel.storage.exceptions import FileNotFoundError as StorageFileNotFoundError


class MemoryDriver:
    """Stores files in a plain dict. Not persistent across restarts."""

    def __init__(self) -> None:
        self._files: dict[str, bytes] = {}

    async def exists(self, path: str) -> bool:
        return path in self._files

    async def get(self, path: str) -> bytes:
        if path not in self._files:
            raise StorageFileNotFoundError(path)
        return self._files[path]

    async def put(self, path: str, contents: bytes | str | BinaryIO) -> bool:
        if isinstance(contents, str):
            self._files[path] = contents.encode()
        elif isinstance(contents, bytes):
            self._files[path] = contents
        else:
            self._files[path] = contents.read()
        return True

    async def delete(self, path: str) -> bool:
        existed = path in self._files
        self._files.pop(path, None)
        return existed

    async def copy(self, src: str, dst: str) -> bool:
        if src not in self._files:
            return False
        self._files[dst] = self._files[src]
        return True

    async def move(self, src: str, dst: str) -> bool:
        if src not in self._files:
            return False
        self._files[dst] = self._files.pop(src)
        return True

    async def files(self, directory: str = "") -> list[str]:
        prefix = directory.rstrip("/") + "/" if directory else ""
        if not prefix:
            return list(self._files.keys())
        return [p for p in self._files if p.startswith(prefix)]

    async def list(self, directory: str = "") -> list[str]:
        return await self.files(directory)

    async def size(self, path: str) -> int:
        if path not in self._files:
            raise StorageFileNotFoundError(path)
        return len(self._files[path])

    def url(self, path: str) -> str:
        return f"memory://{path}"

    def temporary_url(self, path: str, expiry: int) -> str:
        return f"memory://{path}?tmp=1"


__all__ = ["MemoryDriver"]
