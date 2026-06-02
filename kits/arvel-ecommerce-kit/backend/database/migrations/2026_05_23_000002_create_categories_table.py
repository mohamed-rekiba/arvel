"""Create the ``categories`` table (UUID v7 primary key, JSONB name)."""

from __future__ import annotations

from arvel.database import Blueprint, Schema
from arvel.database.schema import IdType

__tablename__ = "categories"


async def up(schema: Schema) -> None:
    def _table(t: Blueprint) -> None:
        t.id(id_type=IdType.UUID)
        t.jsonb("name")
        t.jsonb("slug")
        t.enum("status", values=["draft", "published"]).default("published").nullable(value=False)
        t.datetime("published_at").nullable()
        # Self-referential UUID FK — nullable for top-level categories.
        t.uuid("parent_id").nullable().constrained("categories")
        t.timestamps()
        t.soft_deletes()
        t.index(["parent_id"], name="categories_parent_id_idx")
        t.index(["deleted_at"], name="categories_not_deleted_idx", where="deleted_at IS NULL")
        t.gin_index("categories", "name")
        t.gin_index("categories", "slug")
        t.expression_index("(slug->>'en')", name="categories_slug_en_unique", unique=True)

    schema.create(__tablename__, _table)


async def down(schema: Schema) -> None:
    schema.drop_if_exists(__tablename__)
    schema.run_sql("DROP TYPE IF EXISTS categories_status")
