"""Create users table — canonical authenticatable model (Laravel parity).

Mirrors Laravel's default ``create_users_table`` migration. Apps that want a
custom user model (different ID type, extra columns, different table name)
can ignore this migration and provide their own — the framework does not
hard-depend on this table name or shape; ``JwtGuard`` only needs whatever
``UserProvider`` returns to expose a string-coercible identifier.
"""

from __future__ import annotations

from arvel.database import Blueprint, IdType, Schema

__tablename__ = "users"


async def up(schema: Schema) -> None:
    """Apply the migration."""

    def _table(t: Blueprint) -> None:
        t.id(id_type=IdType.UUID)
        t.string("name", length=255)
        t.string("email", length=254).unique()
        t.datetime("email_verified_at").nullable()
        t.string("password", length=255)
        t.datetime("suspended_at").nullable()
        t.string("remember_token", length=100).nullable()
        t.soft_deletes()
        t.timestamps()

    schema.create(__tablename__, _table)


async def down(schema: Schema) -> None:
    """Roll back the migration."""
    schema.drop_if_exists(__tablename__)
