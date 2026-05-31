"""Create the ``audit_entries`` table — the automatic model change trail.

Carries a composite index on ``(model_type, model_id)`` so per-record history
lookups never fall back to a full-table scan on a production database.
"""

from __future__ import annotations

from arvel.database import Blueprint, Schema


async def up(schema: Schema) -> None:
    """Apply the migration."""

    def _audit_entries(t: Blueprint) -> None:
        t.id()
        t.string("actor_id", length=64).nullable()
        t.enum("action", ["created", "updated", "deleted"])
        t.string("model_type", length=255)
        t.string("model_id", length=64)
        t.json("old_values")
        t.json("new_values")
        t.datetime("created_at", nullable=False).use_current()
        t.index(["model_type", "model_id"], name="audit_entries_model_idx")

    schema.create("audit_entries", _audit_entries)


async def down(schema: Schema) -> None:
    """Roll back the migration."""
    schema.drop_if_exists("audit_entries")
