"""Cookie-based session store — full payload in an encrypted, signed cookie."""

from __future__ import annotations

from typing import Any

from arvel.session.cipher import SessionCipher


class CookieStore:
    """Encrypts session data into a self-contained cookie value.

    Encryption: AES-256-GCM
    Signing:    HMAC-SHA256 over the ciphertext envelope
    Key source: HKDF-SHA256 derived from ``app_key``
    """

    def __init__(
        self, app_key: bytes, lifetime: int = 7200, cookie_name: str = "arvel_session"
    ) -> None:
        self.cookie_name = cookie_name
        self.lifetime = lifetime
        self._cipher = SessionCipher.from_app_key(app_key)
        # Stores the last written cookie value for test introspection
        self.last_written_cookie: str = ""

    # ── SessionStore protocol ─────────────────────────────────────────────────

    async def read(self, session_id: str) -> dict[str, Any]:
        """Not meaningful for cookie store; returns empty dict."""
        return {}

    async def read_from_cookie(self, cookie_value: str) -> dict[str, Any]:
        """Decode and decrypt a cookie value, returning session data or {}."""
        if not cookie_value:
            return {}
        try:
            return self._decode(cookie_value)
        except Exception:
            return {}

    async def write(self, session_id: str, data: dict[str, Any], lifetime: int) -> None:
        self.last_written_cookie = self._encode(data)

    def encode(self, data: dict[str, Any]) -> str:
        """Encrypt + sign the payload into the value StartSession puts in the cookie."""
        return self._encode(data)

    async def destroy(self, session_id: str) -> None:
        pass

    async def gc(self, max_lifetime: int) -> int:
        return 0

    # ── Cookie helpers ────────────────────────────────────────────────────────

    def _encode(self, payload: dict[str, Any]) -> str:
        return self._cipher.encrypt(payload)

    def _decode(self, cookie_value: str) -> dict[str, Any]:
        return self._cipher.decrypt(cookie_value)


__all__ = ["CookieStore"]
