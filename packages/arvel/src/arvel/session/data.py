"""SessionData — in-request, in-memory session state with flash support."""

from __future__ import annotations

import secrets
import uuid
from typing import Any

_FLASH_NEW = "_flash_new"
_FLASH_OLD = "_flash_old"
_SESSION_ID = "_session_id"
_CSRF_KEY = "_csrf_token"


class SessionData:
    """In-memory session state for a single request.

    Populated from the store at request start via ``StartSession`` middleware.
    Written back to the store at response end.
    """

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = dict(data)
        # Old ids queued by regenerate() for the middleware to destroy in the
        # store. Kept off _data so it never gets serialized.
        self._pending_destroy: list[str] = []
        if _SESSION_ID not in self._data:
            self._data[_SESSION_ID] = uuid.uuid7().hex

    # ── Basic operations ──────────────────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._data.get(_FLASH_OLD, {}):
            return self._data[_FLASH_OLD][key]
        return self._data.get(key, default)

    def put(self, key: str, value: Any) -> None:
        self._data[key] = value

    def has(self, key: str) -> bool:
        if key in self._data.get(_FLASH_OLD, {}):
            return True
        return key in self._data

    def forget(self, key: str) -> None:
        self._data.pop(key, None)
        if _FLASH_OLD in self._data:
            self._data[_FLASH_OLD].pop(key, None)

    def flush(self) -> None:
        session_id = self._data.get(_SESSION_ID)
        self._data.clear()
        if session_id:
            self._data[_SESSION_ID] = session_id

    def all(self) -> dict[str, Any]:
        out = {k: v for k, v in self._data.items() if not k.startswith("_")}
        out.update(self._data.get(_FLASH_OLD, {}))
        return out

    def get_id(self) -> str:
        return str(self._data.get(_SESSION_ID, ""))

    def regenerate(self) -> None:
        # Queue the old id for destruction so the backend record can't outlive the
        # rotation — mirrors Laravel's migrate(true). Prevents the pre-login session
        # from lingering after login.
        old_id = self._data.get(_SESSION_ID)
        if isinstance(old_id, str) and old_id:
            self._pending_destroy.append(old_id)
        self._data[_SESSION_ID] = uuid.uuid7().hex

    def drain_pending_destroy(self) -> list[str]:
        """Return ids queued by regenerate() and clear the queue."""
        ids = self._pending_destroy
        self._pending_destroy = []
        return ids

    def invalidate(self) -> None:
        """Flush everything and rotate the id — Laravel's logout/invalidate.

        Clears all data (including the auth key) and queues the old id for
        destruction so nothing survives a logout under the prior id.
        """
        self.flush()
        self.regenerate()

    # ── CSRF token ────────────────────────────────────────────────────────────

    def token(self) -> str:
        """Return the CSRF token, minting one on first access."""
        tok = self._data.get(_CSRF_KEY)
        if not isinstance(tok, str) or not tok:
            tok = secrets.token_urlsafe(32)
            self._data[_CSRF_KEY] = tok
        return tok

    def regenerate_token(self) -> None:
        """Rotate the CSRF token — done on login to bind it to the new session."""
        self._data[_CSRF_KEY] = secrets.token_urlsafe(32)

    # ── Flash operations ──────────────────────────────────────────────────────

    def flash(self, key: str, value: Any) -> None:
        """Store a value in the flash-new bucket (readable on the NEXT request)."""
        if _FLASH_NEW not in self._data:
            self._data[_FLASH_NEW] = {}
        self._data[_FLASH_NEW][key] = value

    def now(self, key: str, value: Any) -> None:
        """Store a value readable only on the CURRENT request."""
        if _FLASH_OLD not in self._data:
            self._data[_FLASH_OLD] = {}
        self._data[_FLASH_OLD][key] = value

    def reflash(self) -> None:
        """Promote old flash to new flash (keep alive for one more request)."""
        old = self._data.pop(_FLASH_OLD, {})
        existing_new = self._data.get(_FLASH_NEW, {})
        merged = {**old, **existing_new}
        if merged:
            self._data[_FLASH_NEW] = merged

    def finalize_flash(self) -> None:
        """Called by StartSession on each request transition.

        Promotes flash-new → flash-old; clears previous flash-old.
        """
        new = self._data.pop(_FLASH_NEW, {})
        self._data.pop(_FLASH_OLD, None)
        if new:
            self._data[_FLASH_OLD] = new

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionData:
        instance = cls.__new__(cls)
        instance._data = dict(data)
        instance._pending_destroy = []
        return instance


__all__ = ["SessionData"]
