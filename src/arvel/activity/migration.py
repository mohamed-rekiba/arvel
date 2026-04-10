"""Framework-shipped activity_entries table migration.

Registered via :func:`register_framework_migration` so that
``arvel db publish`` copies it into the project's migrations directory
when no ``*_create_activity_entries_table.py`` exists yet.
"""

from __future__ import annotations

from arvel.data.migrations import register_framework_migration

_MIGRATION_FILENAME = "007_create_activity_entries_table.py"

_MIGRATION_CONTENT = '''\
"""Create activity_entries table for the activity log recorder.

This migration is shipped by the Arvel activity module.  You can
customise it after publishing — the framework will not overwrite it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.data import Schema

if TYPE_CHECKING:
    from arvel.data import Blueprint


def upgrade() -> None:
    def activity_entries(table: Blueprint) -> None:
        table.id()
        table.string("log_name").index()
        table.text("description")
        table.string("subject_type").nullable().index()
        table.string("subject_id").nullable().index()
        table.string("causer_type").nullable().index()
        table.string("causer_id").nullable().index()
        table.text("properties").nullable()
        table.datetime("timestamp").index()
        table.timestamps()

    Schema.create("activity_entries", activity_entries)


def downgrade() -> None:
    Schema.drop("activity_entries")
'''

register_framework_migration(_MIGRATION_FILENAME, _MIGRATION_CONTENT)
