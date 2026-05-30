"""FlashBag — stand-alone helper exposing typed flash operations.

Used when you want a dedicated flash namespace instead of raw SessionData calls.
"""

from __future__ import annotations

from arvel.session.data import SessionData


class FlashBag:
    """Convenience wrapper around SessionData for flash messaging."""

    def __init__(self, session: SessionData) -> None:
        self._session = session

    def flash(self, key: str, value: object) -> None:
        """Queue *key* for the next request."""
        self._session.flash(key, value)

    def now(self, key: str, value: object) -> None:
        """Make *key* available on the current request only."""
        self._session.now(key, value)

    def reflash(self) -> None:
        """Extend the lifetime of all flash values by one more request."""
        self._session.reflash()

    def get(self, key: str, default: object = None) -> object:
        return self._session.get(key, default)

    def has(self, key: str) -> bool:
        return self._session.has(key)


__all__ = ["FlashBag"]
