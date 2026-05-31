"""Create the ``activity_entries`` table — the business-event activity log.

Carries composite indexes on ``(subject_type, subject_id)`` and
``(causer_type, causer_id)`` so subject/causer lookups stay index-backed.
"""

from __future__ import annotations

from arvel.database import Blueprint, Schema


async def up(schema: Schema) -> None:
    """Apply the migration."""

    def _activity_entries(t: Blueprint) -> None:
        t.id()
        t.string("log_name", length=100)
        t.string("description", length=2000)
        t.string("subject_type", length=255).nullable()
        t.string("subject_id", length=64).nullable()
        t.string("causer_type", length=255).nullable()
        t.string("causer_id", length=64).nullable()
        t.json("properties")
        t.datetime("created_at", nullable=False).use_current()
        t.index(["subject_type", "subject_id"], name="activity_entries_subject_idx")
        t.index(["causer_type", "causer_id"], name="activity_entries_causer_idx")

    schema.create("activity_entries", _activity_entries)


async def down(schema: Schema) -> None:
    """Roll back the migration."""
    schema.drop_if_exists("activity_entries")
