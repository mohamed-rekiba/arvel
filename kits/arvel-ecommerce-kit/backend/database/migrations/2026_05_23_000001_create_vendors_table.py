"""Create the ``vendors`` table (UUID v7 primary key)."""

from __future__ import annotations

from arvel.database import Blueprint, Schema
from arvel.database.schema import IdType

__tablename__ = "vendors"


async def up(schema: Schema) -> None:
    def _table(t: Blueprint) -> None:
        t.id(id_type=IdType.UUID)
        t.string("name", length=200).nullable(value=False)
        t.string("slug", length=200).nullable(value=False)
        t.text("description").nullable()
        t.enum("status", values=["draft", "published"]).default("published").nullable(value=False)
        t.datetime("published_at").nullable()
        t.timestamps()
        t.soft_deletes()
        t.unique(["slug"], name="vendors_slug_unique")
        t.index(["deleted_at"], name="vendors_not_deleted_idx", where="deleted_at IS NULL")

    schema.create(__tablename__, _table)


async def down(schema: Schema) -> None:
    schema.drop_if_exists(__tablename__)
    schema.run_sql("DROP TYPE IF EXISTS vendors_status")
