"""Create jobs table — database queue driver.

Schema decisions:

- ``payload`` is TEXT (JSON-encoded JobEnvelope); no binary data.
- ``available_at`` is the wall-clock time the job is eligible for pickup —
  enables atomic compare-and-set for delayed jobs.
- ``queue`` lets a single table serve multiple logical queues.
- ``(queue, available_at)`` index is the hot path for the worker poll.
"""

from __future__ import annotations

from arvel.database import Blueprint, IdType, Schema

__tablename__ = "jobs"


async def up(schema: Schema) -> None:
    """Apply the migration."""

    def _table(t: Blueprint) -> None:
        t.id(id_type=IdType.BIGINT)
        t.string("queue", length=255)
        t.long_text("payload")
        t.tiny_integer("attempts").default(0)
        t.datetime("available_at").nullable()
        t.datetime("created_at").use_current()
        t.index(["queue", "available_at"], name="jobs_queue_available_idx")

    schema.create(__tablename__, _table)


async def down(schema: Schema) -> None:
    """Roll back the migration."""
    schema.drop_if_exists(__tablename__)
