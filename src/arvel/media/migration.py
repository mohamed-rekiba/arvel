"""Framework-shipped media table migration.

Registered via ``register_framework_migration`` so that ``arvel db migrate``
auto-publishes this file into the project's ``database/migrations/`` directory
if no ``*_create_media_table.py`` migration exists yet.

Users can modify the published copy to add custom columns.
"""

from __future__ import annotations

from arvel.data.migrations import register_framework_migration

_MIGRATION_FILENAME = "003_create_media_table.py"

_MIGRATION_CONTENT = '''\
"""Create the media table.

This migration is shipped by the Arvel media module. You can add custom
columns to the ``media`` table by editing this file — the framework will
not overwrite it once published.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.data import Schema

if TYPE_CHECKING:
    from arvel.data import Blueprint


def upgrade() -> None:
    def media(table: Blueprint) -> None:
        table.id()
        table.string("uuid", 36).index()
        table.string("model_type").index()
        table.integer("model_id").index()
        table.string("collection", 100).default("default").index()
        table.string("name")
        table.string("filename")
        table.string("original_filename")
        table.string("mime_type", 100)
        table.integer("size")
        table.string("disk", 50)
        table.string("path", 1024)
        table.text("conversions").default("{}")
        table.text("custom_properties").default("{}")
        table.integer("order_column").default(0)
        table.timestamps()

    Schema.create("media", media)


def downgrade() -> None:
    Schema.drop("media")
'''

register_framework_migration(_MIGRATION_FILENAME, _MIGRATION_CONTENT)
