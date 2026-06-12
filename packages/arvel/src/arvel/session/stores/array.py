"""In-memory session store — for testing and single-process apps."""

from __future__ import annotations

import time
from typing import Any


class ArraySessionStore:
    """Stores sessions in a plain dict. Not persistent across restarts."""

    def __init__(self, lifetime: int = 7200) -> None:
        self.lifetime = lifetime
        self._store: dict[str, tuple[dict[str, Any], float]] = {}

    async def read(self, session_id: str) -> dict[str, Any]:
        entry = self._store.get(session_id)
        if entry is None:
            return {}
        data, expires_at = entry
        if expires_at and time.time() > expires_at:
            del self._store[session_id]
            return {}
        return dict(data)

    async def write(self, session_id: str, data: dict[str, Any]) -> None:
        expires_at = time.time() + self.lifetime if self.lifetime > 0 else 0.0
        self._store[session_id] = (dict(data), expires_at)

    async def destroy(self, session_id: str) -> None:
        self._store.pop(session_id, None)

    async def gc(self, max_lifetime: int) -> int:
        now = time.time()
        expired = [sid for sid, (_, exp) in self._store.items() if exp and now > exp]
        for sid in expired:
            del self._store[sid]
        return len(expired)


__all__ = ["ArraySessionStore"]
