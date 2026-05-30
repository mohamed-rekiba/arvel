"""Create failed_jobs table — dead-letter store for the queue subsystem.

Schema decisions:

- ``uuid`` is a UUID v4 string — stable identifier for queue:retry / queue:forget.
- ``error`` TEXT is truncated to 65 535 chars before insert (prevents disk exhaustion).
- ``failed_at`` gives human-readable ordering in queue:failed output.
- No foreign key — failed jobs may originate from any driver.
"""

from __future__ import annotations

from arvel.database import Blueprint, IdType, Schema

__tablename__ = "failed_jobs"


async def up(schema: Schema) -> None:
    """Apply the migration."""

    def _table(t: Blueprint) -> None:
        t.id(id_type=IdType.BIGINT)
        t.string("uuid", length=36).unique()
        t.string("queue", length=255)
        t.long_text("payload")
        t.long_text("error")
        t.datetime("failed_at").use_current()
        t.index(["queue"], name="failed_jobs_queue_idx")

    schema.create(__tablename__, _table)


async def down(schema: Schema) -> None:
    """Roll back the migration."""
    schema.drop_if_exists(__tablename__)
