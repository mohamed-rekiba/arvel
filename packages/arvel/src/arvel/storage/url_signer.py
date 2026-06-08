"""TemporaryUrlSigner — HMAC-SHA256 signed temporary URL helper."""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from urllib.parse import urlencode

from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from arvel.support.secure_compare import constant_time_equals


class TemporaryUrlSigner:
    """Signs and verifies temporary storage URLs using HMAC-SHA256.

    URL format: ``{base_url}/{path}?token={b64_hmac}&expires={unix_ts}``
    """

    def __init__(self, app_key: bytes, base_url: str = "http://localhost") -> None:
        self._base_url = base_url.rstrip("/")
        # Derive a sub-key so the same app key can be used for other things.
        self._derived_key: bytes = HKDF(
            algorithm=SHA256(), length=32, salt=None, info=b"arvel-storage-tmp-url"
        ).derive(app_key)

    @property
    def derived_key(self) -> bytes:
        return self._derived_key

    def _hmac(self, path: str, expires: str) -> str:
        message = f"{path}:{expires}".encode()
        raw = hmac.new(self._derived_key, message, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(raw).decode()

    def sign(self, path: str, ttl: int) -> str:
        """Return a signed temporary URL valid for *ttl* seconds."""
        expires = str(int(time.time()) + ttl)
        token = self._hmac(path, expires)
        query = urlencode({"token": token, "expires": expires})
        return f"{self._base_url}/{path.lstrip('/')}?{query}"

    def verify(self, path: str, token: str, expires: str) -> bool:
        """Return True if *token* is valid and not expired."""
        try:
            exp = int(expires)
        except ValueError, TypeError:
            return False
        if time.time() > exp:
            return False
        expected = self._hmac(path, expires)
        return constant_time_equals(expected, token)


__all__ = ["TemporaryUrlSigner"]
