"""Crypt facade — app-level encryption keyed from ``APP_KEY``."""

from __future__ import annotations

import os
from typing import Any, ClassVar

from arvel.encryption.encrypter import Encrypter, MissingAppKeyError


class Crypt:
    """Facade over a process-wide :class:`Encrypter` built from ``APP_KEY``."""

    # Cache per raw APP_KEY so a rotated/monkeypatched key rebuilds the encrypter.
    _cache: ClassVar[dict[str, Encrypter]] = {}
    _override: ClassVar[Encrypter | None] = None

    @classmethod
    def encrypter(cls) -> Encrypter:
        if cls._override is not None:
            return cls._override
        app_key = os.environ.get("APP_KEY")
        if not app_key:
            raise MissingAppKeyError(
                "APP_KEY is not set; run `arvel key:generate` before using encryption."
            )
        enc = cls._cache.get(app_key)
        if enc is None:
            enc = Encrypter.from_app_key(app_key)
            cls._cache[app_key] = enc
        return enc

    @classmethod
    def set_encrypter(cls, encrypter: Encrypter | None) -> None:
        """Pin an encrypter (tests); pass ``None`` to fall back to ``APP_KEY``."""
        cls._override = encrypter

    @classmethod
    def encrypt_string(cls, plaintext: str) -> str:
        return cls.encrypter().encrypt_string(plaintext)

    @classmethod
    def decrypt_string(cls, payload: str) -> str:
        return cls.encrypter().decrypt_string(payload)

    @classmethod
    def encrypt(cls, value: Any) -> str:
        return cls.encrypter().encrypt(value)

    @classmethod
    def decrypt(cls, payload: str) -> Any:
        return cls.encrypter().decrypt(payload)
