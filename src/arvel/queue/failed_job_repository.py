"""Failed job repository — CRUD operations for permanently failed jobs.

Provides methods to record, list, retry, forget, and flush failed jobs.
Used by ``JobRunner`` to persist failures and by CLI commands for management.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from arvel.queue.failed_jobs import FailedJob, redact_payload

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from arvel.queue.contracts import QueueContract
    from arvel.queue.job import Job

DEFAULT_SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "password",
        "token",
        "secret",
        "api_key",
        "access_token",
        "refresh_token",
        "credit_card",
    }
)


class FailedJobRepository:
    """Manages the ``failed_jobs`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record_failure(
        self,
        job: Job,
        error: Exception,
        *,
        attempts: int,
        sensitive_keys: frozenset[str] = DEFAULT_SENSITIVE_KEYS,
    ) -> FailedJob:
        """Record a permanently failed job with redacted payload."""
        payload = redact_payload(job.model_dump(), sensitive_keys)
        failed = FailedJob(
            job_class=f"{type(job).__module__}.{type(job).__qualname__}",
            queue_name=job.queue_name,
            payload=json.dumps(payload),
            exception_class=type(error).__qualname__,
            exception_message=str(error),
            attempts=attempts,
            failed_at=datetime.now(UTC),
        )
        self._session.add(failed)
        await self._session.flush()
        return failed

    async def list_failed(self, *, limit: int = 50) -> list[FailedJob]:
        """Return recent failed jobs ordered by failed_at descending."""
        from sqlalchemy import select

        stmt = select(FailedJob).order_by(FailedJob.failed_at.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def retry_job(self, job_id: int, queue: QueueContract) -> bool:
        """Re-dispatch a failed job and remove from failed table.

        Returns True if the job was found and re-dispatched.
        """
        from sqlalchemy import select

        stmt = select(FailedJob).where(FailedJob.id == job_id)
        result = await self._session.execute(stmt)
        failed = result.scalar_one_or_none()
        if failed is None:
            return False

        from arvel.queue.job import Job

        payload = json.loads(failed.payload)
        job = Job.model_validate(payload)
        await queue.dispatch(job)

        await self._session.delete(failed)
        await self._session.flush()
        return True

    async def forget_job(self, job_id: int) -> bool:
        """Permanently delete a failed job record.

        Returns True if the job was found and deleted.
        """
        from sqlalchemy import select

        stmt = select(FailedJob).where(FailedJob.id == job_id)
        result = await self._session.execute(stmt)
        failed = result.scalar_one_or_none()
        if failed is None:
            return False

        await self._session.delete(failed)
        await self._session.flush()
        return True

    async def flush_all(self) -> int:
        """Purge all failed jobs. Returns count of deleted records."""
        from sqlalchemy import delete, func, select

        count_stmt = select(func.count()).select_from(FailedJob)
        count_result = await self._session.execute(count_stmt)
        count = count_result.scalar_one()

        del_stmt = delete(FailedJob)
        await self._session.execute(del_stmt)
        await self._session.flush()
        return count
