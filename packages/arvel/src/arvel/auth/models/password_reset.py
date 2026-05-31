"""``PasswordReset`` model — one-shot, sha256-hashed reset tokens.

Backs the ``password_resets`` table. Brokers call the model directly:

    digest = sha256(plain).hexdigest()
    await PasswordReset.where(email=normalised).delete()
    await PasswordReset.create(email=normalised, token_hash=digest)

    row = await PasswordReset.where(token_hash=digest).first()
    if row is not None and not row.is_expired(ttl):
        # use row.email …
        await row.delete()

``email`` doubles as the natural key — a UNIQUE/PRIMARY constraint guarantees
that a second ``forgot-password`` call invalidates the first by overwriting
the row. The ``token_hash`` column stores the sha256 hex digest of the
user-facing plaintext; the plaintext only ever travels in the reset email.
"""

from __future__ import annotations

from datetime import UTC, timedelta
from datetime import datetime as _datetime
from typing import ClassVar

from sqlalchemy import String
from sqlalchemy.orm import Mapped

from arvel.database.columns import column, datetime, string
from arvel.database.model import Model


class PasswordReset(Model):
    """One-shot reset token; ``token_hash`` is the only persisted form of the secret.

    No ``Timestamps`` mixin — the table only needs ``created_at`` for the TTL
    check, and the column is declared explicitly so the index name is
    auditable in the migration.
    """

    __tablename__ = "password_resets"
    # created_at only, no updated_at — the insert hook skips the empty UPDATED_AT.
    UPDATED_AT: ClassVar[str] = ""

    __fillable__: ClassVar[list[str] | None] = ["email", "token_hash"]
    __hidden__: ClassVar[list[str] | None] = ["token_hash"]

    email: Mapped[str] = column(String(254), primary_key=True)
    token_hash: Mapped[str] = string(64)
    created_at: Mapped[_datetime] = datetime(nullable=False, init=False, default=None)

    def is_expired(self, ttl: timedelta) -> bool:
        """``True`` when ``now - created_at > ttl`` (UTC-safe)."""
        created = self.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        return _datetime.now(tz=UTC) - created > ttl
