"""Create the polymorphic media table for product images."""

from __future__ import annotations

from arvel.database import Blueprint, Schema

__tablename__ = "media"


async def up(schema: Schema) -> None:
    def _table(t: Blueprint) -> None:
        t.id()
        t.string("model_type").nullable(value=False)
        t.string("model_id", length=36).nullable(value=False)
        t.index(["model_type", "model_id"], name="media_model_type_model_id_index")
        t.uuid("uuid").nullable().unique()
        t.string("collection_name").nullable(value=False).default("default")
        t.string("name").nullable(value=False)
        t.string("file_name").nullable(value=False)
        t.string("mime_type").nullable()
        t.string("disk").nullable(value=False)
        t.string("conversions_disk").nullable()
        t.big_integer("size", unsigned=True).nullable(value=False)
        t.jsonb("manipulations").nullable(value=False).server_default("'{}'::jsonb")
        t.jsonb("custom_properties").nullable(value=False).server_default("'{}'::jsonb")
        t.jsonb("generated_conversions").nullable(value=False).server_default("'{}'::jsonb")
        t.jsonb("responsive_images").nullable(value=False).server_default("'{}'::jsonb")
        t.jsonb("metadata").nullable(value=False).server_default("'{}'::jsonb")
        t.integer("order_column").nullable()
        t.timestamps(nullable=True)
        t.datetime("deleted_at").nullable()
        t.index(["order_column"], name="media_order_column_index")
        t.index(["deleted_at"], name="media_not_deleted_idx", where="deleted_at IS NULL")

    schema.create(__tablename__, _table)


async def down(schema: Schema) -> None:
    """Roll back the migration."""
    schema.drop_if_exists(__tablename__)
