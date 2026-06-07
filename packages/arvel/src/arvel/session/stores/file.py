"""File-based session store."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, cast

import anyio
import anyio.to_thread


class FileSessionStore:
    """Session store backed by JSON files on the local file system."""

    def __init__(self, path: str | Path, lifetime: int = 7200) -> None:
        self._path = Path(path)
        self.lifetime = lifetime

    def _session_file(self, session_id: str) -> Path:
        # Hash the id so a tampered cookie (e.g. "../../etc/passwd") can't escape
        # the session dir. The id is client-controlled; mirrors the file cache store.
        hashed = hashlib.sha256(session_id.encode()).hexdigest()
        return self._path / f"{hashed}.session"

    async def read(self, session_id: str) -> dict[str, Any]:
        file = self._session_file(session_id)

        def _read() -> dict[str, Any]:
            if not file.exists():
                return {}
            try:
                raw: Any = json.loads(file.read_text())
                return cast("dict[str, Any]", raw) if isinstance(raw, dict) else {}
            except json.JSONDecodeError, OSError:
                return {}

        return await anyio.to_thread.run_sync(_read)

    async def write(self, session_id: str, data: dict[str, Any], lifetime: int) -> None:
        file = self._session_file(session_id)

        def _write() -> None:
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(json.dumps(data))

        await anyio.to_thread.run_sync(_write)

    async def destroy(self, session_id: str) -> None:
        file = self._session_file(session_id)

        def _destroy() -> None:
            file.unlink(missing_ok=True)

        await anyio.to_thread.run_sync(_destroy)

    async def gc(self, max_lifetime: int) -> int:
        cutoff = time.time() - max_lifetime

        def _gc() -> int:
            if not self._path.exists():
                return 0
            count = 0
            for f in self._path.glob("*.session"):
                try:
                    if f.stat().st_mtime < cutoff:
                        f.unlink(missing_ok=True)
                        count += 1
                except OSError:
                    pass
            return count

        return await anyio.to_thread.run_sync(_gc)


__all__ = ["FileSessionStore"]
