"""Hash facade — argon2id default (argon2-cffi core dep), bcrypt opt-in.

argon2-cffi is a core arvel dependency (pyproject.toml). bcrypt is optional.
"""

from __future__ import annotations

import importlib
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_DEFAULT_HASHER = PasswordHasher()


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
        try:
            return _DEFAULT_HASHER.verify(hashed, password)
        except VerifyMismatchError:
            return False
        except Exception:  # noqa: BLE001
            return False

    @classmethod
    def needs_rehash(cls, hashed: str) -> bool:
        return _DEFAULT_HASHER.check_needs_rehash(hashed)

    @classmethod
    def make_bcrypt(cls, password: str, rounds: int = 12) -> str:
        try:
            _bcrypt_lib = importlib.import_module("bcrypt")
        except ImportError as exc:
            msg = (
                "bcrypt hashing requires the 'bcrypt' extra. "
                "Install it with: pip install 'arvel[bcrypt]'"
            )
            raise ImportError(msg) from exc
        _bcrypt: Any = _bcrypt_lib
        hashed: bytes = _bcrypt.hashpw(password.encode(), _bcrypt.gensalt(rounds=rounds))
        return hashed.decode()

    @classmethod
    def checkpw(cls, password: str, hashed: str) -> bool:
        """Timing-safe password check via argon2 verify."""
        return cls.check(password, hashed)
