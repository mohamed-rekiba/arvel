"""Framework-shipped notifications table migration.

Registered via :func:`register_framework_migration` so that
``arvel db publish`` copies it into the project's migrations directory
when no ``*_create_notifications_table.py`` exists yet.
"""

from __future__ import annotations

from arvel.data.migrations import register_framework_migration

_MIGRATION_FILENAME = "005_create_notifications_table.py"

_MIGRATION_CONTENT = '''\
"""Create notifications table for database notification channel.

This migration is shipped by the Arvel notifications module.  You can
customise it after publishing — the framework will not overwrite it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.data import Schema

if TYPE_CHECKING:
    from arvel.data import Blueprint


def upgrade() -> None:
    def notifications(table: Blueprint) -> None:
        table.id()
        table.string("notifiable_type").index()
        table.integer("notifiable_id").index()
        table.string("type").index()
        table.text("data")
        table.datetime("read_at").nullable()
        table.timestamps()

    Schema.create("notifications", notifications)


def downgrade() -> None:
    Schema.drop("notifications")
'''

register_framework_migration(_MIGRATION_FILENAME, _MIGRATION_CONTENT)
