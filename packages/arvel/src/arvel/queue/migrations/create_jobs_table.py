"""Create jobs table — database queue driver.

Schema decisions:

- ``payload`` is TEXT (JSON-encoded JobEnvelope); no binary data.
- ``available_at`` / ``created_at`` are Unix epoch *seconds*. The driver
  writes and compares epochs (integers), so these are integer columns, not
  wall-clock timestamps — matching Laravel's jobs table. ``big_integer``
  (BIGINT) keeps them 2038-safe.
- ``priority`` drives the worker's ``ORDER BY priority DESC, available_at ASC``
  pop. It's part of the pop index so the planner orders from the index instead
  of sorting the ready set on every claim.
- ``queue`` lets a single table serve multiple logical queues.

Columns mirror ``arvel.queue.drivers.database.JobRow`` exactly — the driver
is the source of truth, so publishing this migration yields a schema the
driver can actually read and write.
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
        t.tiny_integer("attempts").default(0).nullable(value=False)
        t.big_integer("available_at").nullable(value=False)
        t.big_integer("created_at").nullable(value=False)
        t.integer("priority").default(0).nullable(value=False)
        # Reservation timestamp (epoch seconds), NULL when free. Lets a worker
        # claim a row without deleting it so a crash doesn't lose the job.
        t.big_integer("reserved_at").nullable(value=True)
        t.index(["queue", "priority", "available_at"], name="jobs_queue_priority_available_idx")

    schema.create(__tablename__, _table)


async def down(schema: Schema) -> None:
    """Roll back the migration."""
    schema.drop_if_exists(__tablename__)
