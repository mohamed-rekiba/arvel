"""SessionStore protocol — implemented by all session backends."""

from __future__ import annotations

from typing import Any, Protocol


class SessionStore(Protocol):
    """Async session store interface."""

    async def read(self, session_id: str) -> dict[str, Any]: ...
    async def write(self, session_id: str, data: dict[str, Any], lifetime: int) -> None: ...
    async def destroy(self, session_id: str) -> None: ...
    async def gc(self, max_lifetime: int) -> int: ...


__all__ = ["SessionStore"]
