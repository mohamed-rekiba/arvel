"""AES-256-GCM application encrypter (Laravel's ``Illuminate\\Encryption``).

Distinct from ``database.casts.EncryptedType`` (a column-level type, wire format
v1). The app encrypter is keyed from ``APP_KEY`` via HKDF and uses its own
versioned wire format (v2) so the two never collide on disk.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any, Final

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from arvel.database.exceptions import DecryptionError

_APP_KEY_PREFIX: Final = "base64:"
_VERSION: Final = b"\x02"  # app-encrypter wire format; EncryptedType owns v1
_IV_BYTES: Final = 12
_KEY_BYTES: Final = 32


class MissingAppKeyError(RuntimeError):
    """Raised when encryption is requested but ``APP_KEY`` is unset."""


class Encrypter:
    """Symmetric AES-256-GCM encryption. The key is exactly 32 bytes."""

    def __init__(self, key: bytes) -> None:
        if len(key) != _KEY_BYTES:
            raise ValueError("Encrypter key must be 32 bytes (AES-256).")
        self._aes = AESGCM(key)

    @classmethod
    def from_app_key(cls, app_key: str) -> Encrypter:
        """Derive a 32-byte key from a raw ``APP_KEY`` string (``base64:`` accepted)."""
        raw = base64.b64decode(app_key.removeprefix(_APP_KEY_PREFIX), validate=True)
        key = HKDF(
            algorithm=hashes.SHA256(), length=_KEY_BYTES, salt=None, info=b"arvel-encrypter"
        ).derive(raw)
        return cls(key)

    def encrypt_string(self, plaintext: str) -> str:
        iv = os.urandom(_IV_BYTES)
        ct = self._aes.encrypt(iv, plaintext.encode("utf-8"), None)
        return base64.b64encode(_VERSION + iv + ct).decode("ascii")

    def decrypt_string(self, payload: str) -> str:
        try:
            # binascii.Error subclasses ValueError; bad base64 must not leak.
            raw = base64.b64decode(payload)
        except ValueError as exc:
            raise DecryptionError("Malformed encrypter payload (not valid base64).") from exc
        if raw[:1] != _VERSION:
            raise DecryptionError("Unrecognised encrypter wire-format version.")
        iv, ct = raw[1 : 1 + _IV_BYTES], raw[1 + _IV_BYTES :]
        try:
            return self._aes.decrypt(iv, ct, None).decode("utf-8")
        except Exception as exc:  # AESGCM raises InvalidTag on wrong key / tampering
            raise DecryptionError(
                "Failed to decrypt value (wrong key or tampered ciphertext)."
            ) from exc

    def encrypt(self, value: Any) -> str:
        """JSON-serialize then encrypt — for arbitrary serializable values."""
        return self.encrypt_string(json.dumps(value))

    def decrypt(self, payload: str) -> Any:
        return json.loads(self.decrypt_string(payload))
