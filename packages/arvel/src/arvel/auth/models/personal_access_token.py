"""``PersonalAccessToken`` — token guard storage model.

Polymorphic token store: any ``HasApiTokens`` model can own PATs. The
``token`` column stores the SHA-256 hex digest of the plaintext; the
plaintext is only returned once at creation time.
"""

from __future__ import annotations

import uuid
from datetime import UTC
from datetime import datetime as _datetime
from typing import ClassVar

from arvel.database.columns import field, json
from arvel.database.model import Model, Timestamps


def _new_id() -> str:
    """UUID v7 primary key (time-ordered, stdlib Python 3.14)."""
    return str(uuid.uuid7())


class PersonalAccessToken(Model, Timestamps):
    """Persisted representation of a personal access token.

    Column map (mirrors ``create_personal_access_tokens_table``):

    * ``id``             — UUID v7 primary key
    * ``tokenable_type`` — class name of the owning model (polymorphic)
    * ``tokenable_id``   — PK of the owning model (UUID string)
    * ``name``           — human-readable label (e.g. "mobile app")
    * ``token``          — SHA-256 hex of the plaintext (64 chars); UNIQUE
    * ``abilities``      — JSON array of scope strings (``["*"]`` = all)
    * ``last_used_at``   — updated by the guard on each successful request
    * ``expires_at``     — optional hard expiry; ``None`` = never expires
    """

    __tablename__ = "personal_access_tokens"

    __fillable__: ClassVar[list[str] | None] = [
        "tokenable_type",
        "tokenable_id",
        "name",
        "token",
        "abilities",
        "last_used_at",
        "expires_at",
    ]
    __hidden__: ClassVar[list[str] | None] = ["token"]

    id: str = field(length=36, primary_key=True, init=False, default_factory=_new_id)
    tokenable_type: str
    tokenable_id: str = field(length=36, index=True)
    name: str
    token: str = field(length=64, unique=True)
    abilities: list[str] = json(default=list)
    last_used_at: _datetime | None = None
    expires_at: _datetime | None = None

    @property
    def is_expired(self) -> bool:
        """``True`` when ``expires_at`` is set and in the past."""
        if self.expires_at is None:
            return False
        exp = self.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=UTC)
        return exp <= _datetime.now(tz=UTC)

    def can(self, ability: str) -> bool:
        """``True`` when this token has the given ability or the wildcard ``*``."""
        return "*" in self.abilities or ability in self.abilities


__all__ = ["PersonalAccessToken"]
