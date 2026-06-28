"""Delayed-job storage — the ``jobs`` table backing ``dispatch_after`` (Laravel's delayed queue).

A ``dispatch_after(seconds, job)`` writes a ``QueuedJob`` row with ``available_at`` set in the future
instead of enqueuing immediately; ``QueueManager.release_due_jobs`` pushes the due rows onto the broker
and deletes them. Kept in its own module so importing ``arvel.queue`` doesn't pull ``arvel.database``.
Mirrors the scaffold ``create_jobs_table`` migration columns.
"""

from __future__ import annotations

from typing import Any, ClassVar

from arvel.database import Model


class QueuedJob(Model):
    """A stored, not-yet-due job. ``available_at``/``created_at`` are unix timestamps (ints)."""

    __table_name__ = "jobs"
    __fields__: ClassVar[dict[str, type]] = {
        "queue": str,
        "payload": str,
        "attempts": int,
        "reserved_at": int,
        "available_at": int,
        "created_at": int,
    }
    __fillable__: ClassVar[list[str]] = [
        "queue",
        "payload",
        "attempts",
        "reserved_at",
        "available_at",
        "created_at",
    ]
    __timestamps__ = False  # `created_at` is an explicit unix-ts column, not the ISO timestamps pair

    # accessed by the manager's release loop; dynamic columns (stored in _attributes)
    payload: Any
    queue: Any
    available_at: Any
