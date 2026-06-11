"""File-based session store."""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import anyio
import anyio.to_thread

if TYPE_CHECKING:
    from arvel.session.cipher import SessionCipher


class FileSessionStore:
    """Session store backed by JSON files on the local file system.

    When a ``cipher`` is supplied the on-disk payload is encrypted at rest;
    otherwise it's plain JSON.
    """

    def __init__(
        self,
        path: str | Path,
        lifetime: int = 7200,
        *,
        cipher: SessionCipher | None = None,
    ) -> None:
        self._path = Path(path)
        self.lifetime = lifetime
        self._cipher = cipher

    def _session_file(self, session_id: str) -> Path:
        # Hash the id so a tampered cookie (e.g. "../../etc/passwd") can't escape
        # the session dir. The id is client-controlled; mirrors the file cache store.
        hashed = hashlib.sha256(session_id.encode()).hexdigest()
        return self._path / f"{hashed}.session"

    async def read(self, session_id: str) -> dict[str, Any]:
        file = self._session_file(session_id)
        cutoff = time.time() - self.lifetime if self.lifetime > 0 else None

        def _read() -> dict[str, Any]:
            try:
                # Expire on read so a stale file is treated as empty before GC runs.
                if cutoff is not None and file.stat().st_mtime < cutoff:
                    return {}
                contents = file.read_text()
                if self._cipher is not None:
                    return self._cipher.decrypt(contents)
                raw: Any = json.loads(contents)
                return cast("dict[str, Any]", raw) if isinstance(raw, dict) else {}
            except FileNotFoundError:
                return {}
            except json.JSONDecodeError, OSError, ValueError, TypeError:
                return {}

        return await anyio.to_thread.run_sync(_read)

    async def write(self, session_id: str, data: dict[str, Any], lifetime: int) -> None:
        file = self._session_file(session_id)
        payload = self._cipher.encrypt(data) if self._cipher is not None else json.dumps(data)

        def _write() -> None:
            file.parent.mkdir(parents=True, exist_ok=True)
            # Write to a temp file then atomically replace, so a crash mid-write
            # can't leave a truncated/corrupt session file.
            tmp = file.with_suffix(f".{os.getpid()}.tmp")
            tmp.write_text(payload)
            tmp.replace(file)

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
