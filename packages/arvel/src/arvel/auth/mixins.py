"""Authenticatable and HasApiTokens mixins for ORM models."""

from __future__ import annotations

import hashlib
import secrets
from typing import TYPE_CHECKING, Any, ClassVar, Self

from arvel.auth.models.personal_access_token import PersonalAccessToken


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

    # Annotation only — never a class attribute, so the ORM mapper ignores it
    # and instances don't share state. The token guard sets it per request.
    if TYPE_CHECKING:
        _access_token: PersonalAccessToken | None

    def with_access_token(self, token: PersonalAccessToken) -> Self:
        """Attach the token that authenticated this request. Returns self."""
        self._access_token = token
        return self

    def current_access_token(self) -> PersonalAccessToken | None:
        """The token behind the current request, or None for non-token auth."""
        return getattr(self, "_access_token", None)

    def token_can(self, ability: str) -> bool:
        """True when the current token grants ``ability`` (or holds ``*``)."""
        token = self.current_access_token()
        return token is not None and token.can(ability)

    async def create_token(
        self,
        name: str,
        abilities: list[str] | None = None,
    ) -> str:
        """Persist a hashed token row and return the plain-text token once.

        The plaintext is never stored — only its SHA-256 digest. ``tokenable_type``
        is the fully-qualified class path so the guard can resolve the owner back.
        """
        plain = secrets.token_hex(32)
        await PersonalAccessToken.create(
            tokenable_type=_fqn(type(self)),
            tokenable_id=str(getattr(self, "id", "")),
            name=name,
            token=hashlib.sha256(plain.encode()).hexdigest(),
            abilities=abilities or ["*"],
        )
        return plain

    def create_token_sync(
        self,
        name: str,
        abilities: list[str] | None = None,
    ) -> str:
        """In-memory variant for tests: builds a record without touching the DB."""
        plain = secrets.token_hex(32)
        hashed = hashlib.sha256(plain.encode()).hexdigest()
        abilities = abilities or ["*"]

        record = _TokenRecord(
            tokenable_type=_fqn(type(self)),
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


def _fqn(cls: type[Any]) -> str:
    return f"{cls.__module__}.{cls.__qualname__}"
