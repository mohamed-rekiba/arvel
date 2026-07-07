"""arvel.security — hashing, encryption, signing (core deps; DR-0002).

- ``Hasher`` (a ``HashManager``, `security/hashing.py`) — password hashing, driver-selectable
  (argon2id/bcrypt) on argon2-cffi/bcrypt.
- ``Encrypter`` on **cryptography** (AES-256-GCM, DR-0032) — authenticated symmetric encryption
  keyed by APP_KEY.
- ``Signer`` on **itsdangerous** — tamper-evident signed/timed payloads.

All three are core dependencies (light). Grounded in knowledge/port/15-16 + 04.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
from typing import Any, cast

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from itsdangerous import URLSafeTimedSerializer

from arvel.security.hashing import HashManager

# ``Hasher`` is the manager itself: a no-arg constructor keeps existing call sites/tests working
# while still exposing driver selection (``Hasher(driver="bcrypt")``) for callers that want it.
Hasher = HashManager


def resolve_hasher() -> Hasher:
    """The container-bound hasher (honoring an app's configured params) when an application is
    running, else a default :class:`Hasher`. Lets light-core call sites prefer the framework's
    ``hash`` binding without breaking when constructed outside an app (e.g. in tests)."""
    import contextlib

    from arvel.kernel import app, has_application

    if has_application():
        with contextlib.suppress(Exception):
            return cast("Hasher", app("hash"))
    return Hasher()


class DecryptionFailed(Exception):
    """Ciphertext failed AEAD authentication — tamper, wrong key, or a malformed payload.

    Raised instead of returning a wrong-but-plausible plaintext: GCM's tag check either passes
    or this is raised, there is no silent third outcome.
    """


def _decode_key(key: str | bytes) -> bytes:
    """32 raw bytes, or a string — a ``base64:<b64>``-prefixed or bare base64
    string (standard or urlsafe alphabet, so a key from any common base64 key generator
    decodes) that resolves to exactly 32 bytes (AES-256)."""
    if isinstance(key, bytes):
        decoded = key
    else:
        text = key.removeprefix("base64:")
        try:
            decoded = base64.b64decode(text, validate=True)
        except binascii.Error:
            try:
                decoded = base64.urlsafe_b64decode(text)
            except binascii.Error as exc:
                raise ValueError(f"invalid encryption key encoding: {exc}") from exc
    if len(decoded) != 32:
        raise ValueError("encryption key must decode to exactly 32 bytes (AES-256-GCM)")
    return decoded


class Encrypter:
    """Symmetric encryption on cryptography's AESGCM (AES-256-GCM), keyed by APP_KEY (DR-0032).

    Payload: ``v1.<b64 nonce>.<b64 ciphertext+tag>``. ``encrypt``/``decrypt`` are serialize-aware
    (a JSON envelope — ``Crypt::encrypt`` parity, minus pickle's RCE-on-key-leak history);
    ``encrypt_string``/``decrypt_string`` skip serialization for plain strings (``encryptString``
    parity). Pass ``previous_keys`` to support key rotation: data is always encrypted under the
    current (first) key, but ``decrypt``/``decrypt_string`` accept ciphertext from any provided
    key, and ``rotate`` re-encrypts an old token under the current key.
    """

    _VERSION = "v1"

    def __init__(self, key: str | bytes, *previous_keys: str | bytes) -> None:
        self._keys = [_decode_key(k) for k in (key, *previous_keys)]

    def encrypt_string(self, value: str) -> str:
        return self._seal(value.encode())

    def decrypt_string(self, token: str) -> str:
        return self._open(token).decode()

    def encrypt(self, value: Any) -> str:
        return self._seal(json.dumps({"j": value}).encode())

    def decrypt(self, token: str) -> Any:
        # a verified-but-non-envelope payload (e.g. an encrypt_string token) is a caller
        # contract break, surfaced uniformly as DecryptionFailed — never a leaked json error
        try:
            envelope = json.loads(self._open(token))
            return envelope["j"]
        except json.JSONDecodeError, TypeError, KeyError:
            raise DecryptionFailed("token does not hold a serialized envelope") from None

    def rotate(self, token: str) -> str:
        """Re-encrypt a token (from any held key) under the current primary key, without
        touching its serialization — a JSON-enveloped token stays enveloped."""
        return self._seal(self._open(token))

    def _seal(self, plaintext: bytes) -> str:
        nonce = os.urandom(12)
        ciphertext = AESGCM(self._keys[0]).encrypt(nonce, plaintext, None)
        return f"{self._VERSION}.{_b64e(nonce)}.{_b64e(ciphertext)}"

    def _open(self, token: str) -> bytes:
        try:
            version, nonce_b64, ct_b64 = token.split(".")
        except ValueError as exc:
            raise DecryptionFailed("malformed ciphertext payload") from exc
        if version != self._VERSION:
            raise DecryptionFailed(f"unsupported payload version: {version!r}")
        try:
            nonce, ciphertext = _b64d(nonce_b64), _b64d(ct_b64)
        except binascii.Error as exc:
            raise DecryptionFailed("malformed ciphertext payload") from exc
        for key in self._keys:
            try:
                return AESGCM(key).decrypt(nonce, ciphertext, None)
            except InvalidTag, ValueError:
                continue
        raise DecryptionFailed("ciphertext did not verify under any known key")

    @staticmethod
    def generate_key() -> str:
        return f"base64:{base64.b64encode(AESGCM.generate_key(bit_length=256)).decode()}"


def _b64e(data: bytes) -> str:
    return base64.b64encode(data).decode()


def _b64d(data: str) -> bytes:
    return base64.b64decode(data, validate=True)


class SignatureInvalid(Exception):
    """A signed value failed verification — tampered, wrong key, or expired.

    The module's own vocabulary (like :class:`DecryptionFailed`): callers never
    have to catch the signing library's exception types."""


class Signer:
    """Tamper-evident signing on itsdangerous."""

    def __init__(self, secret: str) -> None:
        self._serializer = URLSafeTimedSerializer(secret)

    def sign(self, value: Any) -> str:
        return self._serializer.dumps(value)

    def unsign(self, signed: str, max_age: int | None = None) -> Any:
        try:
            return self._serializer.loads(signed, max_age=max_age)
        except Exception as exc:
            raise SignatureInvalid(str(exc)) from exc


__all__ = [
    "DecryptionFailed",
    "Encrypter",
    "HashManager",
    "Hasher",
    "SignatureInvalid",
    "Signer",
    "resolve_hasher",
]
