"""FileStore — JSON file-based cache. One file per key, stored under a configurable path."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import anyio
import anyio.to_thread

from arvel.cache.exceptions import TagsNotSupported


class FileStore:
    """Cache store backed by JSON files on disk.

    Keys are hashed (SHA-256) to generate safe filenames.
    TTL is stored as a Unix timestamp inside the file.
    """

    def __init__(self, path: Path, prefix: str = "arvel_cache") -> None:
        self._path = path
        self._prefix = prefix

    def _file_for(self, key: str) -> Path:
        hashed = hashlib.sha256(f"{self._prefix}:{key}".encode()).hexdigest()
        return self._path / f"{hashed}.json"

    def _is_expired(self, expires_at: float) -> bool:
        return expires_at != 0.0 and time.time() > expires_at

    async def put(self, key: str, value: Any, ttl: int | None = None) -> None:
        expires_at = 0.0 if ttl is None else time.time() + ttl
        payload = json.dumps({"value": value, "expires_at": expires_at})
        file_path = self._file_for(key)
        await anyio.to_thread.run_sync(file_path.write_text, payload)

    async def get(self, key: str, default: Any = None) -> Any | None:
        file_path = self._file_for(key)
        if not file_path.exists():
            return default
        try:
            raw = await anyio.to_thread.run_sync(file_path.read_text)
            data = json.loads(raw)
        except json.JSONDecodeError, OSError:
            return default
        if self._is_expired(data.get("expires_at", 0.0)):
            await anyio.to_thread.run_sync(lambda: file_path.unlink(missing_ok=True))
            return default
        return data["value"]

    async def forget(self, key: str) -> bool:
        file_path = self._file_for(key)
        if file_path.exists():
            await anyio.to_thread.run_sync(lambda: file_path.unlink(missing_ok=True))
            return True
        return False

    async def has(self, key: str) -> bool:
        file_path = self._file_for(key)
        if not file_path.exists():
            return False
        try:
            raw = await anyio.to_thread.run_sync(file_path.read_text)
            data = json.loads(raw)
        except json.JSONDecodeError, OSError:
            return False
        if self._is_expired(data.get("expires_at", 0.0)):
            await anyio.to_thread.run_sync(lambda: file_path.unlink(missing_ok=True))
            return False
        return True

    async def flush(self) -> None:
        def _flush() -> None:
            for f in self._path.glob("*.json"):
                f.unlink(missing_ok=True)

        await anyio.to_thread.run_sync(_flush)

    async def forever(self, key: str, value: Any) -> None:
        await self.put(key, value, ttl=None)

    async def many(self, keys: list[str]) -> dict[str, Any | None]:
        return {k: await self.get(k) for k in keys}

    async def put_many(self, values: dict[str, Any], ttl: int | None = None) -> None:
        for k, v in values.items():
            await self.put(k, v, ttl=ttl)

    def tags(self, tags: list[str]) -> None:
        raise TagsNotSupported("FileStore")


__all__ = ["FileStore"]
