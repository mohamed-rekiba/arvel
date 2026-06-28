"""arvel.security — hashing, encryption, signing (core deps; DR-0002).

- ``Hasher`` on **pwdlib** (argon2) — password hashing.
- ``Encrypter`` on **cryptography** (Fernet) — symmetric encryption keyed by APP_KEY.
- ``Signer`` on **itsdangerous** — tamper-evident signed/timed payloads.

All three are core dependencies (light). Grounded in knowledge/port/15-16 + 04.
"""

from __future__ import annotations

from typing import Any, cast

from cryptography.fernet import Fernet, MultiFernet
from itsdangerous import URLSafeTimedSerializer
from pwdlib import PasswordHash


class Hasher:
    """Password hashing on pwdlib (argon2)."""

    def __init__(self) -> None:
        self._hasher = PasswordHash.recommended()

    def make(self, plain: str) -> str:
        return self._hasher.hash(plain)

    def check(self, plain: str, hashed: str) -> bool:
        return self._hasher.verify(plain, hashed)

    def needs_rehash(self, plain: str, hashed: str) -> bool:
        _valid, updated = self._hasher.verify_and_update(plain, hashed)
        return updated is not None


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


class Encrypter:
    """Symmetric encryption on cryptography's Fernet, keyed by APP_KEY.

    Pass ``previous_keys`` to support key rotation: data is always encrypted under the current
    (first) key, but ``decrypt`` accepts ciphertext from any provided key, and ``rotate``
    re-encrypts an old token under the current key (via cryptography's ``MultiFernet``).
    """

    def __init__(self, key: str | bytes, *previous_keys: str | bytes) -> None:
        keys = [key, *previous_keys]
        self._fernet = MultiFernet(
            [Fernet(k if isinstance(k, bytes) else k.encode()) for k in keys]
        )

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, token: str) -> str:
        return self._fernet.decrypt(token.encode()).decode()

    def rotate(self, token: str) -> str:
        """Re-encrypt a token (from any held key) under the current primary key."""
        return self._fernet.rotate(token.encode()).decode()

    @staticmethod
    def generate_key() -> str:
        return Fernet.generate_key().decode()


class Signer:
    """Tamper-evident signing on itsdangerous."""

    def __init__(self, secret: str) -> None:
        self._serializer = URLSafeTimedSerializer(secret)

    def sign(self, value: Any) -> str:
        return self._serializer.dumps(value)

    def unsign(self, signed: str, max_age: int | None = None) -> Any:
        return self._serializer.loads(signed, max_age=max_age)


__all__ = ["Encrypter", "Hasher", "Signer"]
