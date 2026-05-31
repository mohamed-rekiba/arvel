"""App-level encryption — AES-256-GCM ``Encrypter`` keyed from ``APP_KEY``."""

from __future__ import annotations

from arvel.encryption.encrypter import Encrypter, MissingAppKeyError

__all__ = ["Encrypter", "MissingAppKeyError"]
