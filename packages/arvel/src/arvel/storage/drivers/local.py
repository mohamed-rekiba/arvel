"""Local filesystem storage driver."""

from __future__ import annotations

from pathlib import Path
from typing import BinaryIO
from urllib.parse import unquote

import anyio
import anyio.to_thread

from arvel.storage.exceptions import StorageFileNotFoundError, StoragePathError
from arvel.storage.url_signer import TemporaryUrlSigner


class LocalDriver:
    """Stores files on the local filesystem under a configured root.

    Prevents path-traversal attacks by resolving all paths relative to root.
    """

    def __init__(
        self,
        root: str | Path,
        base_url: str = "http://localhost/storage",
        app_key: bytes = b"",
    ) -> None:
        self._root = Path(root).resolve()
        self._base_url = base_url.rstrip("/")
        self._signer: TemporaryUrlSigner | None = (
            TemporaryUrlSigner(app_key, base_url) if app_key else None
        )

    def _safe_path(self, path: str) -> Path:
        # Decode URL-encoded characters to catch encoded traversal attempts.
        decoded = unquote(path)
        if "\x00" in decoded:
            raise StoragePathError(path)
        if decoded.startswith("/"):
            raise StoragePathError(path)
        resolved = (self._root / decoded).resolve()
        if not str(resolved).startswith(str(self._root) + "/") and resolved != self._root:
            raise StoragePathError(path)
        return resolved

    async def exists(self, path: str) -> bool:
        full = self._safe_path(path)
        return await anyio.to_thread.run_sync(full.exists)

    async def get(self, path: str) -> bytes:
        full = self._safe_path(path)

        def _read() -> bytes:
            if not full.exists():
                raise StorageFileNotFoundError(path)
            return full.read_bytes()

        return await anyio.to_thread.run_sync(_read)

    async def put(self, path: str, contents: bytes | str | BinaryIO) -> bool:
        full = self._safe_path(path)

        if isinstance(contents, str):
            data: bytes = contents.encode()
        elif isinstance(contents, bytes):
            data = contents
        else:
            data = contents.read()

        def _write() -> None:
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_bytes(data)

        await anyio.to_thread.run_sync(_write)
        return True

    async def delete(self, path: str) -> bool:
        full = self._safe_path(path)

        def _delete() -> bool:
            if not full.exists():
                return False
            full.unlink()
            return True

        return await anyio.to_thread.run_sync(_delete)

    async def copy(self, src: str, dst: str) -> bool:
        src_full = self._safe_path(src)
        dst_full = self._safe_path(dst)

        def _copy() -> bool:
            if not src_full.exists():
                return False
            dst_full.parent.mkdir(parents=True, exist_ok=True)
            dst_full.write_bytes(src_full.read_bytes())
            return True

        return await anyio.to_thread.run_sync(_copy)

    async def move(self, src: str, dst: str) -> bool:
        src_full = self._safe_path(src)
        dst_full = self._safe_path(dst)

        def _move() -> bool:
            if not src_full.exists():
                return False
            dst_full.parent.mkdir(parents=True, exist_ok=True)
            src_full.rename(dst_full)
            return True

        return await anyio.to_thread.run_sync(_move)

    async def files(self, directory: str = "") -> list[str]:
        """List all files under *directory* (relative paths from root)."""
        base = self._safe_path(directory) if directory else self._root

        def _list() -> list[str]:
            if not base.exists():
                return []
            return [str(p.relative_to(self._root)) for p in base.rglob("*") if p.is_file()]

        return await anyio.to_thread.run_sync(_list)

    async def list(self, directory: str = "") -> list[str]:
        return await self.files(directory)

    async def size(self, path: str) -> int:
        full = self._safe_path(path)

        def _size() -> int:
            if not full.exists():
                raise StorageFileNotFoundError(path)
            return full.stat().st_size

        return await anyio.to_thread.run_sync(_size)

    def url(self, path: str) -> str:
        return f"{self._base_url}/{path.lstrip('/')}"

    def temporary_url(self, path: str, expiry: int) -> str:
        if self._signer is None:
            raise RuntimeError("LocalDriver requires app_key to generate temporary URLs")
        return self._signer.sign(path, ttl=expiry)


__all__ = ["LocalDriver"]
