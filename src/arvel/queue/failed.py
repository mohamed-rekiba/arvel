"""Failed-job persistence — the ``failed_jobs`` table.

When a job exhausts its retries the worker records a ``FailedJob`` row (the serialized job payload +
the exception). ``retry()`` (the ``queue:retry`` command) rebuilds the job, re-dispatches it, and
deletes the record. Kept in its own module so importing ``arvel.queue`` doesn't pull ``arvel.database``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

import sqlalchemy as sa

from arvel.database import HasUuids, Model


class FailedJob(HasUuids, Model):
    """A dead job: ``queue`` + serialized ``payload`` + ``exception`` text + ``failed_at`` (UUID id,
    no created/updated timestamps — the ``failed_jobs`` only stamps ``failed_at``)."""

    __table_name__ = "failed_jobs"
    # the failed_jobs has only failed_at, no created_at/updated_at — opt out of the
    # __timestamps__=True default (DR-0029) or every SELECT names a column the migration never created.
    __timestamps__: ClassVar[bool] = False
    # payload/exception are TEXT: a serialized job / full traceback both exceed VARCHAR(255).
    __fields__: ClassVar[dict[str, Any]] = {
        "queue": str,
        "payload": sa.Text(),
        "exception": sa.Text(),
        "failed_at": datetime,
    }
    __fillable__: ClassVar[list[str]] = ["queue", "payload", "exception", "failed_at"]
    __casts__: ClassVar[dict[str, Any]] = {"failed_at": "datetime"}

    async def retry(self) -> Any:
        """Re-dispatch the serialized job and delete this record."""
        from arvel.kernel import app, has_application
        from arvel.queue import QueueManager
        from arvel.queue.serialization import deserialize_instance

        job = await deserialize_instance(self.payload)
        # a manual retry is a FRESH dispatch with the job's full tries/backoff budget — the
        # exhausted attempt counter the failure record carried must not ride along (with it,
        # a tries=3 job re-entered at its final attempt and bounced straight back here)
        job.__arvel_attempts__ = 0
        manager = (
            app().make("queue") if has_application() and app().bound("queue") else QueueManager()
        )
        result = await manager.push_instance(job)
        await self.delete()
        return result


async def failed_jobs() -> list[FailedJob]:
    """The failed-job records, newest first — the ``QueueManager.failed_jobs()`` admin surface."""
    return list(await FailedJob.order_by("failed_at", "desc").get())


async def retry_failed(failed_id: str | None = None) -> list[FailedJob]:
    """Re-dispatch failed jobs — one by id, or every one. Returns
    the records that were retried (each is re-pushed and its record deleted)."""
    if failed_id is None:
        jobs = list(await FailedJob.get())
    else:
        found = await FailedJob.find(failed_id)
        jobs = [found] if found is not None else []
    for job in jobs:
        await job.retry()
    return jobs
