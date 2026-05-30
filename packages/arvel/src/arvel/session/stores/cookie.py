"""Cookie-based session store — full payload in an encrypted, signed cookie."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from typing import Any, cast

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


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
        self._enc_key = HKDF(
            algorithm=SHA256(), length=32, salt=None, info=b"arvel-session-enc"
        ).derive(app_key)
        self._mac_key = HKDF(
            algorithm=SHA256(), length=32, salt=None, info=b"arvel-session-mac"
        ).derive(app_key)
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

    async def destroy(self, session_id: str) -> None:
        pass

    async def gc(self, max_lifetime: int) -> int:
        return 0

    # ── Cookie helpers ────────────────────────────────────────────────────────

    def _encode(self, payload: dict[str, Any]) -> str:
        plaintext = json.dumps(payload).encode()
        nonce = os.urandom(12)
        ciphertext = AESGCM(self._enc_key).encrypt(nonce, plaintext, None)
        envelope = nonce + ciphertext
        mac = hmac.new(self._mac_key, envelope, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(mac + envelope).decode()

    def _decode(self, cookie_value: str) -> dict[str, Any]:
        try:
            raw = base64.urlsafe_b64decode(cookie_value.encode())
        except Exception as exc:
            raise ValueError("Malformed cookie value") from exc

        if len(raw) < 32 + 12 + 16:
            raise ValueError("Cookie value too short")

        mac, envelope = raw[:32], raw[32:]
        expected_mac = hmac.new(self._mac_key, envelope, hashlib.sha256).digest()
        if not hmac.compare_digest(mac, expected_mac):
            raise ValueError("Cookie signature mismatch — possible tampering")

        nonce, ciphertext = envelope[:12], envelope[12:]
        try:
            plaintext = AESGCM(self._enc_key).decrypt(nonce, ciphertext, None)
        except Exception as exc:
            raise ValueError("Cookie decryption failed") from exc

        parsed: Any = json.loads(plaintext)
        if not isinstance(parsed, dict):
            raise TypeError("Cookie payload must be a JSON object")
        data: dict[str, Any] = cast("dict[str, Any]", parsed)
        return data


__all__ = ["CookieStore"]
