"""Framework-shipped audit_entries table migration.

Registered via :func:`register_framework_migration` so that
``arvel db publish`` copies it into the project's migrations directory
when no ``*_create_audit_entries_table.py`` exists yet.
"""

from __future__ import annotations

from arvel.data.migrations import register_framework_migration

_MIGRATION_FILENAME = "006_create_audit_entries_table.py"

_MIGRATION_CONTENT = '''\
"""Create audit_entries table for the Auditable mixin.

This migration is shipped by the Arvel audit module.  You can customise
it after publishing — the framework will not overwrite it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.data import Schema

if TYPE_CHECKING:
    from arvel.data import Blueprint


def upgrade() -> None:
    def audit_entries(table: Blueprint) -> None:
        table.id()
        table.string("actor_id").nullable().index()
        table.string("action")
        table.string("model_type").index()
        table.string("model_id").index()
        table.text("old_values").nullable()
        table.text("new_values").nullable()
        table.datetime("timestamp").index()
        table.timestamps()

    Schema.create("audit_entries", audit_entries)


def downgrade() -> None:
    Schema.drop("audit_entries")
'''

register_framework_migration(_MIGRATION_FILENAME, _MIGRATION_CONTENT)
