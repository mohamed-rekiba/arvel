"""``RefreshToken`` model — opaque refresh tokens, hashed at rest.

Backs the ``refresh_tokens`` table (see
``arvel/auth/migrations/create_refresh_tokens_table.py``). Brokers call the
model directly — no repository, no raw SQL. Standard Eloquent flow:

    plain = generate_refresh_token()
    await RefreshToken.create(
        user_id=user.id,
        token_hash=hash_refresh_token(plain),
        expires_at=refresh_token_expires_at(ttl),
    )

    record = await RefreshToken.where(token_hash=h).first()
    if record is not None and record.is_active:
        # use ``record.user_id`` …
        await record.delete()

The ``token_hash`` column stores the sha256 hex digest of the user-facing
plaintext (64 chars). The plaintext only ever travels in the
``__Host-refresh`` cookie and is never persisted.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import ClassVar

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from arvel.database.attributes import accessor
from arvel.database.model import Model, Timestamps


def _new_id() -> str:
    """UUID v7 default for the ``id`` column (time-ordered, stdlib Python 3.14)."""
    return str(uuid.uuid7())


class RefreshToken(Model, Timestamps):
    """Opaque refresh-token row; ``token_hash`` is the only persisted form of the secret.

    Mass-assignment is locked down via ``__fillable__`` — the broker is the
    only legitimate writer, but defence-in-depth still pays off if a future
    DTO carrier accidentally ferries an attacker-controlled ``user_id`` into
    a ``.create(**payload)`` call.

    ``__hidden__`` keeps ``token_hash`` out of any ``to_dict()`` /
    serialised representation; even an audit listener that decides to log
    the model never accidentally surfaces the hash.
    """

    __tablename__ = "refresh_tokens"

    __fillable__: ClassVar[list[str] | None] = [
        "user_id",
        "token_hash",
        "expires_at",
        "revoked_at",
    ]
    __hidden__: ClassVar[list[str] | None] = ["token_hash"]

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        init=False,
        default_factory=_new_id,
    )
    user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    @accessor
    def is_expired(self) -> bool:
        """``True`` when the row's ``expires_at`` is in the past (UTC)."""
        exp = self.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=UTC)
        return exp <= datetime.now(tz=UTC)

    @accessor
    def is_active(self) -> bool:
        """``True`` when the row is neither revoked nor expired."""
        return self.revoked_at is None and not self.is_expired
