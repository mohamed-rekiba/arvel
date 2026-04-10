"""Storage contract — ABC for swappable file storage drivers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import builtins
    from datetime import timedelta


class StorageContract(ABC):
    """Abstract base class for file storage drivers.

    Implementations: LocalStorage (filesystem), S3Storage (S3-compatible),
    NullStorage (dry-run).
    """

    @abstractmethod
    async def put(
        self,
        path: str,
        data: bytes,
        *,
        content_type: str | None = None,
    ) -> None:
        """Write *data* to *path*. Raises StoragePathError on invalid path."""

    @abstractmethod
    async def get(self, path: str) -> bytes:
        """Return file content at *path*. Raises FileNotFoundError if absent."""

    @abstractmethod
    async def delete(self, path: str) -> bool:
        """Remove the file at *path*. Return True if it existed."""

    @abstractmethod
    async def exists(self, path: str) -> bool:
        """Return True if a file exists at *path*."""

    @abstractmethod
    async def url(self, path: str) -> str:
        """Return a public URL for the file at *path*."""

    @abstractmethod
    async def temporary_url(self, path: str, expiration: timedelta) -> str:
        """Return a time-limited signed URL. Not all drivers support this."""

    @abstractmethod
    async def size(self, path: str) -> int:
        """Return file size in bytes. Raises FileNotFoundError if absent."""

    @abstractmethod
    async def list(self, prefix: str = "") -> builtins.list[str]:
        """List file paths under *prefix*."""
