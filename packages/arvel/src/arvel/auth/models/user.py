"""Framework ``User`` model — canonical authenticatable ORM model.

Mirrors Laravel's default User model. Apps that need a different schema
can extend this class, replace it entirely, or bind a custom
``UserProvider`` in their ``AuthServiceProvider``.

The model deliberately avoids exposing ``password`` in ``to_dict()``
via ``__hidden__`` — the same defence-in-depth that ``RefreshToken``
applies to ``token_hash``.
"""

from __future__ import annotations

import uuid
from datetime import UTC
from datetime import datetime as _datetime
from typing import ClassVar

from sqlalchemy import String
from sqlalchemy.orm import Mapped

from arvel.auth.mixins import Authenticatable, HasApiTokens
from arvel.database.columns import column, datetime, string, text
from arvel.database.model import Model, SoftDeletes, Timestamps


def _new_id() -> str:
    """UUID v7 primary key (time-ordered, stdlib Python 3.14)."""
    return str(uuid.uuid7())


class User(Model, Timestamps, SoftDeletes, Authenticatable, HasApiTokens):
    """Default authenticatable user model.

    Column map (mirrors ``create_users_table`` migration):

    * ``id``               — UUID v7 primary key
    * ``name``             — display name
    * ``email``            — unique, normalised to lower-case by the broker
    * ``email_verified_at``— ``None`` until the verification URL is consumed
    * ``password``         — argon2id hash; never serialised (``__hidden__``)
    * ``suspended_at``     — non-``None`` blocks login (``AccountSuspendedError``)
    * ``remember_token``   — opaque session-cookie fallback (optional)

    Plus ``created_at``, ``updated_at`` (Timestamps) and ``deleted_at``
    (SoftDeletes).
    """

    __tablename__ = "users"

    _auth_password_field: ClassVar[str] = "password"  # noqa: S105

    __fillable__: ClassVar[list[str] | None] = [
        "name",
        "email",
        "password",
        "email_verified_at",
        "suspended_at",
        "remember_token",
        "locale",
    ]
    __hidden__: ClassVar[list[str] | None] = ["password", "remember_token"]

    id: Mapped[str] = column(String(36), primary_key=True, init=False, default_factory=_new_id)
    # Required columns (no default — must precede columns with defaults)
    name: Mapped[str] = string(255)
    email: Mapped[str] = string(254, unique=True, index=True)
    password: Mapped[str] = string(255)
    # Optional columns
    email_verified_at: Mapped[_datetime | None] = datetime(nullable=True, default=None)
    suspended_at: Mapped[_datetime | None] = datetime(nullable=True, default=None)
    remember_token: Mapped[str | None] = string(100, nullable=True, default=None)
    locale: Mapped[str | None] = text(nullable=True, default=None)

    @property
    def is_verified(self) -> bool:
        """``True`` when the email has been confirmed."""
        return self.email_verified_at is not None

    @property
    def is_suspended(self) -> bool:
        """``True`` when the account is currently suspended."""
        return self.suspended_at is not None

    def suspend(self) -> User:
        """Mark the account as suspended (caller must ``await user.save()``)."""
        self.suspended_at = _datetime.now(tz=UTC)
        return self

    def unsuspend(self) -> User:
        """Clear the suspension (caller must ``await user.save()``)."""
        self.suspended_at = None
        return self


__all__ = ["User"]
