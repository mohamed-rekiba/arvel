"""StorageFake + Storage.fake()/.assert_*() — FR-016-011."""

from __future__ import annotations

from collections.abc import AsyncIterator
from types import TracebackType
from typing import TYPE_CHECKING, BinaryIO, Self

if TYPE_CHECKING:
    from arvel.facades.storage import StorageManagerLike


class _MemoryDisk:
    """In-memory disk that satisfies the ``StorageDisk`` Protocol.

    ``files`` is exposed publicly so ``StorageFake`` (same module) can drive
    synchronous assertions without going through the async surface.
    """

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    async def exists(self, path: str) -> bool:
        return path in self.files

    async def get(self, path: str) -> bytes:
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path]

    async def put(self, path: str, contents: bytes | str | BinaryIO) -> bool:
        if isinstance(contents, bytes):
            self.files[path] = contents
        elif isinstance(contents, str):
            self.files[path] = contents.encode()
        else:
            self.files[path] = contents.read()
        return True

    async def delete(self, path: str) -> bool:
        existed = path in self.files
        self.files.pop(path, None)
        return existed

    async def list(self, directory: str = "") -> list[str]:
        prefix = directory.rstrip("/") + "/" if directory else ""
        if not prefix:
            return list(self.files.keys())
        return [p for p in self.files if p.startswith(prefix)]

    def url(self, path: str) -> str:
        return f"memory:///{path}"

    def temporary_url(self, path: str, expiry: int) -> str:
        return f"memory:///{path}?tmp=1&expiry={expiry}"

    async def size(self, path: str) -> int:
        return len(self.files.get(path, b""))

    async def files_in(self, prefix: str) -> AsyncIterator[str]:
        for p in self.files:
            if p.startswith(prefix):
                yield p


class StorageFake:
    """In-memory storage manager — one disk per requested name."""

    def __init__(self) -> None:
        self._disks: dict[str | None, _MemoryDisk] = {}

    def disk(self, name: str | None = None) -> _MemoryDisk:
        if name not in self._disks:
            self._disks[name] = _MemoryDisk()
        return self._disks[name]

    def has_path(self, path: str, disk: str | None = None) -> bool:
        """True iff ``path`` exists on the named fake disk."""
        return path in self.disk(disk).files


class StorageFakeContext:
    """Context manager: swap the bound StorageManager with a StorageFake."""

    def __init__(self, disk: str | None = None) -> None:  # noqa: ARG002 — reserved for parity
        self._original: StorageManagerLike | None = None
        self.fake = StorageFake()

    def disk(self, name: str | None = None) -> _MemoryDisk:
        """Proxy to the underlying StorageFake so tests can do ``ctx.disk("s3")``."""
        return self.fake.disk(name)

    def __enter__(self) -> Self:
        from arvel.facades.storage import Storage

        self._original = Storage.swap_manager(self.fake)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        from arvel.facades.storage import Storage

        Storage.swap_manager(self._original)


__all__ = ["StorageFake", "StorageFakeContext"]
