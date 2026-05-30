"""Authenticatable and HasApiTokens mixins for ORM models."""

from __future__ import annotations

import hashlib
import secrets
from typing import Any, ClassVar


class Authenticatable:
    """Mixin that marks an ORM model as usable with authentication guards."""

    _auth_password_field: ClassVar[str] = "password_hash"  # noqa: S105

    def get_auth_id(self) -> str:
        return str(getattr(self, "id", ""))

    def get_auth_password(self) -> str:
        return str(getattr(self, self._auth_password_field, ""))


class _TokenRecord:
    """In-memory token record returned by create_token_sync for testing."""

    def __init__(
        self,
        tokenable_type: str,
        tokenable_id: str,
        name: str,
        token: str,
        abilities: list[str],
    ) -> None:
        self.tokenable_type = tokenable_type
        self.tokenable_id = tokenable_id
        self.name = name
        self.token = token  # SHA-256 hash
        self.abilities = abilities
        self.expires_at: Any = None
        self.last_used_at: Any = None


class HasApiTokens:
    """Mixin for ORM models that own personal access tokens."""

    def create_token_sync(
        self,
        name: str,
        abilities: list[str] | None = None,
    ) -> str:
        """Generate a token, persist a hashed record, return the plain-text token once."""
        plain = secrets.token_hex(32)
        hashed = hashlib.sha256(plain.encode()).hexdigest()
        abilities = abilities or ["*"]

        record = _TokenRecord(
            tokenable_type=type(self).__qualname__,
            tokenable_id=str(getattr(self, "id", "")),
            name=name,
            token=hashed,
            abilities=abilities,
        )
        self._persist_token(record)
        return plain

    def _persist_token(self, record: _TokenRecord) -> _TokenRecord:
        """Override in ORM subclasses to save the record to the database."""
        return record
