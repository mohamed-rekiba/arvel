"""Authenticated-encryption envelope for session payloads.

AES-256-GCM for confidentiality, HMAC-SHA256 over the envelope for integrity,
keys derived from the app key via HKDF-SHA256. Shared by the cookie store and
the server-side stores (file/database/redis) so `SESSION_ENCRYPT` means the same
thing everywhere.
"""

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

_MAC_LEN = 32
_NONCE_LEN = 12
_GCM_TAG_LEN = 16


class SessionCipher:
    """Encrypts/decrypts a session dict to/from a self-contained token."""

    __slots__ = ("_enc_key", "_mac_key")

    def __init__(self, enc_key: bytes, mac_key: bytes) -> None:
        self._enc_key = enc_key
        self._mac_key = mac_key

    @classmethod
    def from_app_key(cls, app_key: bytes) -> SessionCipher:
        enc_key = HKDF(
            algorithm=SHA256(), length=32, salt=None, info=b"arvel-session-enc"
        ).derive(app_key)
        mac_key = HKDF(
            algorithm=SHA256(), length=32, salt=None, info=b"arvel-session-mac"
        ).derive(app_key)
        return cls(enc_key, mac_key)

    def encrypt(self, payload: dict[str, Any]) -> str:
        plaintext = json.dumps(payload).encode()
        nonce = os.urandom(_NONCE_LEN)
        ciphertext = AESGCM(self._enc_key).encrypt(nonce, plaintext, None)
        envelope = nonce + ciphertext
        mac = hmac.new(self._mac_key, envelope, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(mac + envelope).decode()

    def decrypt(self, token: str) -> dict[str, Any]:
        try:
            raw = base64.urlsafe_b64decode(token.encode())
        except Exception as exc:
            raise ValueError("Malformed session token") from exc

        if len(raw) < _MAC_LEN + _NONCE_LEN + _GCM_TAG_LEN:
            raise ValueError("Session token too short")

        mac, envelope = raw[:_MAC_LEN], raw[_MAC_LEN:]
        expected_mac = hmac.new(self._mac_key, envelope, hashlib.sha256).digest()
        if not hmac.compare_digest(mac, expected_mac):
            raise ValueError("Session signature mismatch — possible tampering")

        nonce, ciphertext = envelope[:_NONCE_LEN], envelope[_NONCE_LEN:]
        try:
            plaintext = AESGCM(self._enc_key).decrypt(nonce, ciphertext, None)
        except Exception as exc:
            raise ValueError("Session decryption failed") from exc

        parsed: Any = json.loads(plaintext)
        if not isinstance(parsed, dict):
            raise TypeError("Session payload must be a JSON object")
        return cast("dict[str, Any]", parsed)


__all__ = ["SessionCipher"]
