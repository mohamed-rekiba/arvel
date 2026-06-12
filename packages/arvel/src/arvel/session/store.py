"""SessionStore protocol — implemented by all session backends."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


class SessionStore(Protocol):
    """Async session store interface."""

    async def read(self, session_id: str) -> dict[str, Any]: ...
    async def write(self, session_id: str, data: dict[str, Any]) -> None: ...
    async def destroy(self, session_id: str) -> None: ...
    async def gc(self, max_lifetime: int) -> int: ...


@runtime_checkable
class CookieBackedStore(Protocol):
    """A store whose cookie carries the encrypted payload itself.

    Server-side stores key on an opaque session id; this kind packs the whole
    session into the cookie value. ``StartSession`` checks for this to read the
    payload from the cookie and write the ciphertext back as the cookie value.
    """

    async def read_from_cookie(self, cookie_value: str) -> dict[str, Any]: ...
    def encode(self, data: dict[str, Any]) -> str: ...


__all__ = ["CookieBackedStore", "SessionStore"]
