"""SessionData — in-request, in-memory session state with flash support."""

from __future__ import annotations

import uuid
from typing import Any

_FLASH_NEW = "_flash_new"
_FLASH_OLD = "_flash_old"
_SESSION_ID = "_session_id"


class SessionData:
    """In-memory session state for a single request.

    Populated from the store at request start via ``StartSession`` middleware.
    Written back to the store at response end.
    """

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = dict(data)
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
        self._data[_SESSION_ID] = uuid.uuid7().hex

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
        return instance


__all__ = ["SessionData"]
