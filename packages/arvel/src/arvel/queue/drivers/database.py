"""Database driver — persists jobs in the `jobs` ORM table.

The driver added the ``priority`` column and folded ``push_delayed``
into ``push`` — delay is sourced from ``envelope.delay``. Pop applies
``ORDER BY priority DESC, available_at ASC LIMIT 1``.
"""

from __future__ import annotations

import time
from math import ceil
from typing import Any

from sqlalchemy import BigInteger, Column, Index, Integer, String, Text, delete, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql import Select

from arvel.logging.facade import Log
from arvel.queue.envelope import JobEnvelope

logger = Log.channel(__name__)


class _Base(DeclarativeBase):
    pass


class JobRow(_Base):
    """ORM mapping for the ``jobs`` table.

    Public so tests and operators can build sessions against the same schema
    without accessing private symbols.
    """

    __tablename__ = "jobs"

    # Integer (not BigInteger) so SQLite treats it as the autoincrementing
    # rowid alias; reads a BIGINT id from the migration-built table fine.
    id: Any = Column(Integer, primary_key=True, autoincrement=True)
    queue: Any = Column(String(255), nullable=False)
    payload: Any = Column(Text, nullable=False)
    attempts: Any = Column(Integer, nullable=False, default=0)
    # Unix epoch seconds. BIGINT, not INTEGER — 32-bit caps out in 2038.
    available_at: Any = Column(BigInteger, nullable=False)
    created_at: Any = Column(BigInteger, nullable=False)
    priority: Any = Column(Integer, nullable=False, default=0)

    # Pop claims one row with WHERE queue=? AND available_at<=now
    # ORDER BY priority DESC, available_at ASC. Putting priority before
    # available_at lets the planner serve the ordering from the index instead
    # of sorting the whole ready set on every claim. Also covers the queue-only
    # filters used by size()/clear() via the leading column.
    __table_args__ = (
        Index("jobs_queue_priority_available_idx", "queue", "priority", "available_at"),
    )


def build_pop_statement(*, queue: str, now: int) -> Select[tuple[JobRow]]:
    """Build the row-claim query used by workers."""
    return (
        select(JobRow)
        .where(JobRow.queue == queue, JobRow.available_at <= now)
        .order_by(JobRow.priority.desc(), JobRow.available_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )


class DatabaseConnection:
    """Queue driver backed by the `jobs` SQL table."""

    def __init__(
        self,
        config: Any = None,  # DatabaseQueueConfig | None
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        engine: AsyncEngine | None = None,
    ) -> None:
        self._engine: AsyncEngine = engine or create_async_engine("sqlite+aiosqlite:///:memory:")
        if session_factory is not None:
            self._session_factory = session_factory
        else:
            self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)

    @property
    def engine(self) -> AsyncEngine:
        """The underlying async engine."""
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """The session factory used by this driver."""
        return self._session_factory

    async def setup(self) -> None:
        """Create tables in the test/SQLite database."""
        async with self._engine.begin() as conn:
            await conn.run_sync(_Base.metadata.create_all)

    async def push(self, envelope: JobEnvelope, queue: str = "default") -> None:
        now_float = time.time()
        now = int(now_float)
        delay = max(0, envelope.delay)
        row = JobRow(
            queue=queue,
            payload=envelope.to_json(),
            attempts=envelope.attempts,
            available_at=now if delay == 0 else ceil(now_float + delay),
            created_at=now,
            priority=int(envelope.priority),
        )
        async with self._session_factory() as session, session.begin():
            session.add(row)

    async def pop_blocking(
        self, queue: str = "default", timeout: float = 3.0
    ) -> JobEnvelope | None:
        now = int(time.time())
        async with self._session_factory() as session, session.begin():
            stmt = build_pop_statement(queue=queue, now=now)
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            if row is None:
                return None
            payload_json: str = row.payload
            row_id: int = row.id
            del_stmt = delete(JobRow).where(JobRow.id == row_id)
            await session.execute(del_stmt)

        try:
            envelope = JobEnvelope.from_json(payload_json)
        except (ValueError, TypeError) as exc:
            logger.warning(
                "queue.envelope.malformed",
                driver="database",
                queue=queue,
                row_id=row_id,
                payload_size=len(payload_json),
                exception_type=type(exc).__name__,
                reason=str(exc),
            )
            return None

        from arvel.queue.registry import JobRegistry

        if envelope.job_class not in JobRegistry:
            await self._record_unknown_class(envelope, queue)
            return None

        return envelope

    async def size(self, queue: str = "default") -> int:
        from sqlalchemy import func

        async with self._session_factory() as session:
            stmt = select(func.count()).select_from(JobRow).where(JobRow.queue == queue)
            result = await session.execute(stmt)
            return result.scalar_one()

    async def clear(self, queue: str = "default") -> None:
        async with self._session_factory() as session, session.begin():
            await session.execute(delete(JobRow).where(JobRow.queue == queue))

    async def close(self) -> None:
        pass

    async def _record_unknown_class(self, envelope: JobEnvelope, queue: str) -> None:
        """Write a FailedJob row for payloads whose class is not in the allowlist."""
        try:
            from arvel.queue.failed_job_store import FailedJobStore

            store = FailedJobStore(self._session_factory)
            store.set_engine(self._engine)
            await store.create(
                envelope=envelope,
                queue=queue,
                error=f"Unknown job class: {envelope.job_class!r}",
            )
        # Failed jobs route to failed_jobs; the worker must keep ticking.
        except Exception:  # nosec B110
            pass


__all__ = ["DatabaseConnection"]
