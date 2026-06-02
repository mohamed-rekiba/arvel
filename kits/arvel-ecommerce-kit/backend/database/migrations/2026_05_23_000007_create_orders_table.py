"""Create the ``orders`` table (UUID v7 PK, integer user_id FK)."""

from __future__ import annotations

from arvel.database import Blueprint, Schema
from arvel.database.schema import IdType

__tablename__ = "orders"


async def up(schema: Schema) -> None:
    def _table(t: Blueprint) -> None:
        t.id(id_type=IdType.UUID)
        # users.id is integer (framework auth)
        t.foreign_id("user_id").nullable(value=False).constrained("users").restrict_on_delete()
        t.enum(
            "status",
            values=["pending", "confirmed", "processing", "shipped", "delivered", "cancelled"],
        ).default("pending").nullable(value=False)
        t.decimal("total", precision=10, scale=2).nullable(value=False)
        t.json("shipping_address").nullable(value=False)
        t.text("note").nullable()
        t.timestamps()
        t.soft_deletes()
        t.index(["user_id", "created_at"], name="orders_user_created_idx")
        t.index(
            ["status", "created_at"],
            name="orders_status_active_idx",
            where="deleted_at IS NULL",
        )

    schema.create(__tablename__, _table)


async def down(schema: Schema) -> None:
    schema.drop_if_exists(__tablename__)
    schema.run_sql("DROP TYPE IF EXISTS orders_status")
