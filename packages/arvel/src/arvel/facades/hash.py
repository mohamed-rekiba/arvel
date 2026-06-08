"""Hash facade — argon2id default (argon2-cffi core dep), bcrypt opt-in.

argon2-cffi is a core arvel dependency (pyproject.toml). bcrypt is optional.
"""

from __future__ import annotations

import importlib
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_DEFAULT_HASHER = PasswordHasher()

# bcrypt hashes are self-identifying: $2a$/$2b$/$2y$. argon2 hashes start with $argon2.
_BCRYPT_PREFIXES = ("$2a$", "$2b$", "$2y$")
_BCRYPT_DEFAULT_ROUNDS = 12


def _is_bcrypt(hashed: str) -> bool:
    return hashed.startswith(_BCRYPT_PREFIXES)


class Hash:
    """Facade for password hashing operations."""

    @classmethod
    def make(cls, password: str, **kwargs: object) -> str:
        if kwargs:
            hasher = PasswordHasher(**kwargs)  # type: ignore[arg-type]
            return hasher.hash(password)
        return _DEFAULT_HASHER.hash(password)

    @classmethod
    def make_argon2(cls, password: str, **kwargs: object) -> str:
        return cls.make(password, **kwargs)

    @classmethod
    def check(cls, password: str, hashed: str) -> bool:
        # Empty hash never matches (Laravel parity). Dispatch on the hash's own
        # prefix so a bcrypt hash verifies with bcrypt, not argon2.
        if not hashed:
            return False
        if _is_bcrypt(hashed):
            return cls._check_bcrypt(password, hashed)
        try:
            return _DEFAULT_HASHER.verify(hashed, password)
        except VerifyMismatchError:
            return False
        except Exception:  # noqa: BLE001
            return False

    @classmethod
    def needs_rehash(cls, hashed: str) -> bool:
        # Default algorithm is argon2id, so any bcrypt hash wants an upgrade
        # (Laravel's password_needs_rehash flags an algorithm mismatch too).
        if _is_bcrypt(hashed):
            return True
        return _DEFAULT_HASHER.check_needs_rehash(hashed)

    @classmethod
    def make_bcrypt(cls, password: str, rounds: int = _BCRYPT_DEFAULT_ROUNDS) -> str:
        _bcrypt = cls._load_bcrypt()
        hashed: bytes = _bcrypt.hashpw(password.encode(), _bcrypt.gensalt(rounds=rounds))
        return hashed.decode()

    @staticmethod
    def _load_bcrypt() -> Any:
        try:
            return importlib.import_module("bcrypt")
        except ImportError as exc:
            msg = (
                "bcrypt hashing requires the 'bcrypt' extra. "
                "Install it with: pip install 'arvel[bcrypt]'"
            )
            raise ImportError(msg) from exc

    @classmethod
    def _check_bcrypt(cls, password: str, hashed: str) -> bool:
        # Can't verify a bcrypt hash without the extra — treat as a non-match,
        # not a crash, so the auth path degrades gracefully.
        try:
            _bcrypt = cls._load_bcrypt()
        except ImportError:
            return False
        try:
            return bool(_bcrypt.checkpw(password.encode(), hashed.encode()))
        except ValueError, TypeError:
            return False

    @classmethod
    def checkpw(cls, password: str, hashed: str) -> bool:
        """Timing-safe password check; dispatches to argon2 or bcrypt by hash prefix."""
        return cls.check(password, hashed)
