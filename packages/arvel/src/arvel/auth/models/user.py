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
from datetime import UTC, datetime
from typing import ClassVar

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from arvel.auth.mixins import Authenticatable, HasApiTokens
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

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        init=False,
        default_factory=_new_id,
    )
    # Required columns (no default — must precede columns with defaults)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False, index=True)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    # Optional columns
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    suspended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    remember_token: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        default=None,
    )
    locale: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None,
    )

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
        self.suspended_at = datetime.now(tz=UTC)
        return self

    def unsuspend(self) -> User:
        """Clear the suspension (caller must ``await user.save()``)."""
        self.suspended_at = None
        return self


__all__ = ["User"]
