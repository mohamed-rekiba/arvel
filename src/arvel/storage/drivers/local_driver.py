"""LocalStorage — stores files on the local filesystem."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import builtins
    from datetime import timedelta

from arvel.storage.contracts import StorageContract
from arvel.storage.exceptions import StoragePathError


def _sanitize_path(path: str) -> str:
    if not path:
        raise StoragePathError(path, "empty path")
    if "\x00" in path:
        raise StoragePathError(path, "contains null byte")
    if Path(path).is_absolute():
        raise StoragePathError(path, "absolute path not allowed")
    if ".." in path.split("/"):
        raise StoragePathError(path, "directory traversal not allowed")
    return path


class LocalStorage(StorageContract):
    """Stores files on the local filesystem under a configurable root."""

    def __init__(self, root: str, base_url: str = "/storage") -> None:
        self._root = Path(root)
        self._base_url = base_url.rstrip("/")

    def _resolve(self, path: str) -> Path:
        clean = _sanitize_path(path)
        return self._root / clean

    async def put(
        self,
        path: str,
        data: bytes,
        *,
        content_type: str | None = None,
    ) -> None:
        full = self._resolve(path)
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(data)

    async def get(self, path: str) -> bytes:
        full = self._resolve(path)
        if not full.exists():
            raise FileNotFoundError(f"File not found: {path}")
        return full.read_bytes()

    async def delete(self, path: str) -> bool:
        full = self._resolve(path)
        if not full.exists():
            return False
        full.unlink()
        return True

    async def exists(self, path: str) -> bool:
        return self._resolve(path).exists()

    async def url(self, path: str) -> str:
        _sanitize_path(path)
        return f"{self._base_url}/{path}"

    async def temporary_url(self, path: str, expiration: timedelta) -> str:
        raise NotImplementedError("LocalStorage does not support signed URLs")

    async def size(self, path: str) -> int:
        full = self._resolve(path)
        if not full.exists():
            raise FileNotFoundError(f"File not found: {path}")
        return full.stat().st_size

    async def list(self, prefix: str = "") -> builtins.list[str]:
        base = self._root / prefix if prefix else self._root
        if not base.exists():
            return []
        results: builtins.list[str] = []
        for item in base.rglob("*"):
            if item.is_file():
                results.append(str(item.relative_to(self._root)))
        return sorted(results)
