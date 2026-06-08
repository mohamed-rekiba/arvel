"""Create the ``password_resets`` table — DB-backed reset-token storage.

Password reset uses a one-shot DB-backed token
flow. The broker mints a 32-byte URL-safe plaintext, stores its sha256 hex
digest here keyed by email, and emails the plaintext to the user. On
``POST /api/auth/reset-password`` the broker rehashes the supplied token,
looks it up, and (on success) DELETEs the row so it can't be replayed.

Schema:

- ``email`` — lookup key. UNIQUE so a second forgot-password call
 invalidates the first (UPSERT semantics in the broker).
- ``token_hash`` — sha256 hex digest (64 chars) of the user-facing token.
 Never stored as plaintext.
- ``created_at`` — supports the TTL check (default 60 minutes via
 ``config.auth.passwords.ttl_minutes``) and the
 ``arvel auth:clear-resets`` console command.

Apps wanting a different schema (e.g. composite keys for multi-tenant
setups) can ignore this migration and ship their own; the broker only
needs the three columns above.
"""

from __future__ import annotations

from arvel.database import Blueprint, Schema

__tablename__ = "password_resets"


async def up(schema: Schema) -> None:
    """Apply the migration."""

    def _table(t: Blueprint) -> None:
        t.string("email", length=254).nullable(value=False)
        t.string("token_hash", length=64).nullable(value=False)
        t.datetime("created_at").nullable(value=False).use_current()
        t.unique(["email"], name="password_resets_email_unique")
        t.index(["created_at"], name="password_resets_created_at_idx")

    schema.create(__tablename__, _table)


async def down(schema: Schema) -> None:
    """Roll back the migration."""
    schema.drop_if_exists(__tablename__)
