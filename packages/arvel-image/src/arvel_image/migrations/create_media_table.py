"""Create the ``media`` table — Spatie laravel-medialibrary v11 parity.

Mirrors the schema in
`spatie/laravel-medialibrary <https://spatie.be/docs/laravel-medialibrary/v11>`_:
a single polymorphic ``media`` table associating files with any model
through ``model_type`` + ``model_id``. JSON columns hold media-library
metadata (``manipulations``, ``custom_properties``, ``generated_conversions``,
``responsive_images``); the actual file bytes live on whichever Arvel
storage disk the consumer configures (``disk`` / ``conversions_disk``).

NOT NULL columns are marked explicitly so the stub stays faithful to
Spatie's schema regardless of any future framework-default change.

Indexes:

- composite ``(model_type, model_id)`` for the polymorphic lookup
  (added by ``t.morphs("model")``).
- ``order_column`` for ``->orderBy('order_column')``-style queries.
- ``uuid`` is unique so non-guessable URLs round-trip cleanly.
"""

from __future__ import annotations

from arvel.database import Blueprint, Schema

__tablename__ = "media"


async def up(schema: Schema) -> None:
    """Apply the migration."""

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
        t.json("manipulations").nullable(value=False)
        t.json("custom_properties").nullable(value=False)
        t.json("generated_conversions").nullable(value=False)
        t.json("responsive_images").nullable(value=False)
        t.integer("order_column").nullable()
        t.timestamps(nullable=True)
        t.index(["order_column"], name="media_order_column_index")

    schema.create(__tablename__, _table)


async def down(schema: Schema) -> None:
    """Roll back the migration."""
    schema.drop_if_exists(__tablename__)
