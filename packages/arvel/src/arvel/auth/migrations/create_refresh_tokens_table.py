"""Create the ``refresh_tokens`` table — opaque token rotation store.

Holds SHA-256 hex digests of refresh-token plaintexts — never plaintext.

Schema:

- ``id`` — UUID primary key.
- ``user_id`` — string FK; the column is generic (UUID or int-as-string)
 so the framework does not assume a specific user-table
 shape. Apps with a different user table override the
 ``AuthBroker`` and skip the model.
- ``token_hash`` — sha256 hex digest (64 chars) of the user-facing token.
 UNIQUE so a stolen-row replay attack reduces to one row.
- ``expires_at`` — refresh TTL boundary (default 14 days via
 ``config.auth.refresh.ttl_seconds``).
- ``revoked_at`` — explicit revocation timestamp; the broker's reuse-detection
 path stamps this before deleting so the row's history is
 auditable if the audit listener is wired up.

Apps wanting a different schema (e.g. composite keys for multi-tenant
setups) ignore this migration and ship their own; the
:class:`arvel.auth.RefreshToken` model only needs the columns above.
"""

from __future__ import annotations

from arvel.database import Blueprint, IdType, Schema

__tablename__ = "refresh_tokens"


async def up(schema: Schema) -> None:
    """Apply the migration."""

    def _table(t: Blueprint) -> None:
        t.id(id_type=IdType.UUID)
        t.string("user_id", length=36)
        t.string("token_hash", length=64).unique()
        t.datetime("expires_at")
        t.datetime("revoked_at").nullable()
        t.timestamps()
        t.index(["user_id"], name="refresh_tokens_user_idx")

    schema.create(__tablename__, _table)


async def down(schema: Schema) -> None:
    """Roll back the migration."""
    schema.drop_if_exists(__tablename__)
