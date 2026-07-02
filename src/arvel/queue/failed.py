"""Failed-job persistence — the ``failed_jobs`` table (Laravel parity).

When a job exhausts its retries the worker records a ``FailedJob`` row (the serialized job payload +
the exception). ``retry()`` rebuilds the job, re-dispatches it, and deletes the record (Laravel
``queue:retry``). Kept in its own module so importing ``arvel.queue`` doesn't pull ``arvel.database``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

import sqlalchemy as sa

from arvel.database import HasUuids, Model


class FailedJob(HasUuids, Model):
    """A dead job: ``queue`` + serialized ``payload`` + ``exception`` text + ``failed_at`` (UUID id,
    no created/updated timestamps — Laravel's ``failed_jobs`` only stamps ``failed_at``)."""

    __table_name__ = "failed_jobs"
    # Laravel's failed_jobs has NO created_at/updated_at (only failed_at) — opt out of the
    # __timestamps__=True default (DR-0029) or every SELECT names columns the canonical migration
    # never created (caught by the kit's queue-rail integration test on real PG).
    __timestamps__: ClassVar[bool] = False
    # `failed_at` is a real DateTime column (DR-0023): the datetime cast stores/reads a real datetime
    # (read back as a Date), matching the migration's DATETIME column. `payload`/`exception` are TEXT
    # (a serialized job / a full traceback both exceed VARCHAR(255)) — matching the migration.
    __fields__: ClassVar[dict[str, Any]] = {
        "queue": str,
        "payload": sa.Text(),
        "exception": sa.Text(),
        "failed_at": datetime,
    }
    __fillable__: ClassVar[list[str]] = ["queue", "payload", "exception", "failed_at"]
    __casts__: ClassVar[dict[str, Any]] = {"failed_at": "datetime"}

    async def retry(self) -> Any:
        """Re-dispatch the serialized job and delete this record (Laravel ``queue:retry``)."""
        from arvel.kernel import app, has_application
        from arvel.queue import QueueManager, deserialize_instance

        job = await deserialize_instance(self.payload)
        manager = (
            app().make("queue") if has_application() and app().bound("queue") else QueueManager()
        )
        result = await manager.push_instance(job)
        await self.delete()
        return result
