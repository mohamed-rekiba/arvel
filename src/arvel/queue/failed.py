"""Failed-job persistence — the ``failed_jobs`` table (Laravel parity).

When a job exhausts its retries the worker records a ``FailedJob`` row (the serialized job payload +
the exception). ``retry()`` rebuilds the job, re-dispatches it, and deletes the record (Laravel
``queue:retry``). Kept in its own module so importing ``arvel.queue`` doesn't pull ``arvel.database``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

from arvel.database import HasUuids, Model


class FailedJob(HasUuids, Model):
    """A dead job: ``queue`` + serialized ``payload`` + ``exception`` text + ``failed_at`` (UUID id,
    no created/updated timestamps — Laravel's ``failed_jobs`` only stamps ``failed_at``)."""

    __table_name__ = "failed_jobs"
    # `failed_at` casts to an ISO string itself, so the migration's DATETIME column is cast-compatible.
    __fields__: ClassVar[dict[str, type]] = {
        "queue": str,
        "payload": str,
        "exception": str,
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
