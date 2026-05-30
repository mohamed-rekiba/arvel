"""Create personal_access_tokens table — token guard storage.

Schema decisions:

- ``id`` is a UUID v7 primary key (time-sortable, no sequential enumeration).
- ``token`` is 64 chars — SHA-256 hex of the plaintext.
- ``tokenable_type`` + ``tokenable_id`` are polymorphic — any
  ``HasApiTokens`` model.
- ``abilities`` is a JSON array of string scopes.
"""

from __future__ import annotations

from arvel.database import Blueprint, IdType, Schema

__tablename__ = "personal_access_tokens"


async def up(schema: Schema) -> None:
    """Apply the migration."""

    def _table(t: Blueprint) -> None:
        t.id(id_type=IdType.UUID)
        t.string("tokenable_type", length=255)
        t.string("tokenable_id", length=36)
        t.string("name", length=255)
        t.string("token", length=64).unique()
        t.json("abilities").default("[]")
        t.datetime("last_used_at").nullable()
        t.datetime("expires_at").nullable()
        t.timestamps()
        t.index(["tokenable_type", "tokenable_id"], name="pat_tokenable_idx")

    schema.create(__tablename__, _table)


async def down(schema: Schema) -> None:
    """Roll back the migration."""
    schema.drop_if_exists(__tablename__)
