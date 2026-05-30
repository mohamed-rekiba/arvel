"""Create the ``carts`` table (UUID v7 PK, integer user_id FK)."""

from __future__ import annotations

from arvel.database import Blueprint, Schema
from arvel.database.schema import IdType

__tablename__ = "carts"


async def up(schema: Schema) -> None:
    def _table(t: Blueprint) -> None:
        t.id(id_type=IdType.UUID)
        # users.id is integer (from framework's auth migrations)
        t.foreign_id("user_id").nullable(value=False).constrained("users").cascade_on_delete()
        t.timestamps()
        t.unique(["user_id"], name="carts_user_id_unique")

    schema.create(__tablename__, _table)


async def down(schema: Schema) -> None:
    schema.drop_if_exists(__tablename__)
