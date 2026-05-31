"""``AuditValues`` — a JSON column that optionally encrypts its payload at rest.

In plain mode the dict is stored as native JSON. When ``encrypt=True`` the dict
is JSON-serialized, encrypted with the app encrypter (AES-256-GCM, keyed from
``APP_KEY``), and the ciphertext string is stored as a JSON string. The key is
resolved lazily at bind/result time, so importing the model never requires
``APP_KEY`` to be present unless encryption is actually enabled.
"""

from __future__ import annotations

import json
from typing import Any, cast

from sqlalchemy import JSON, TypeDecorator
from sqlalchemy.engine import Dialect


class AuditValues(TypeDecorator[dict[str, Any]]):
    """JSON dict column, optionally encrypted. ``None`` passes through."""

    impl = JSON
    cache_ok = False

    def __init__(self, *, encrypt: bool = False) -> None:
        self._encrypt = encrypt
        super().__init__()

    def process_bind_param(self, value: dict[str, Any] | None, dialect: Dialect) -> Any:
        if value is None:
            return None
        if not self._encrypt:
            return value
        from arvel.facades.crypt import Crypt

        return Crypt.encrypt_string(json.dumps(value))

    def process_result_value(self, value: Any, dialect: Dialect) -> dict[str, Any] | None:
        if value is None:
            return None
        if self._encrypt:
            from arvel.facades.crypt import Crypt

            decoded: object = json.loads(Crypt.decrypt_string(str(value)))
        else:
            decoded = value
        if not isinstance(decoded, dict):
            return {}
        items = cast("dict[object, object]", decoded)
        return {str(k): v for k, v in items.items()}


__all__ = ["AuditValues"]
