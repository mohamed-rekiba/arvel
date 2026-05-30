"""FailedJobStore — CRUD for the `failed_jobs` dead-letter table."""

from __future__ import annotations

import uuid as uuid_lib

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from arvel.queue.envelope import JobEnvelope
from arvel.queue.models.failed_job import FailedJob, FailedJobBase

_MAX_ERROR_LEN = 1_000  # NFR-008-012: cap error messages to prevent information disclosure


class FailedJobStore:
    """Reads and writes `FailedJob` rows. One instance per application."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._engine: AsyncEngine | None = None

    def set_engine(self, engine: AsyncEngine) -> None:
        """Set the async engine used for schema setup (``setup()``)."""
        self._engine = engine

    @classmethod
    def create_in_memory(cls) -> FailedJobStore:
        """Convenience factory for tests — returns an in-memory SQLite store."""
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            engine, expire_on_commit=False
        )
        instance = cls(factory)
        instance._engine = engine
        return instance

    async def setup(self) -> None:
        """Create the failed_jobs table (test / in-memory use)."""
        engine = getattr(self, "_engine", None)
        if engine is None:
            return
        async with engine.begin() as conn:
            await conn.run_sync(FailedJobBase.metadata.create_all)

    async def create(self, *, envelope: JobEnvelope, queue: str, error: str) -> FailedJob:
        truncated_error = error[:_MAX_ERROR_LEN]
        row = FailedJob(
            uuid=str(uuid_lib.uuid4()),
            queue=queue,
            payload=envelope.to_json(),
            error=truncated_error,
        )
        async with self._session_factory() as session, session.begin():
            session.add(row)
        return row

    async def find(self, job_uuid: str) -> FailedJob | None:
        async with self._session_factory() as session:
            result = await session.execute(select(FailedJob).where(FailedJob.uuid == job_uuid))
            return result.scalar_one_or_none()

    async def list_all(self) -> list[FailedJob]:
        async with self._session_factory() as session:
            result = await session.execute(select(FailedJob))
            return list(result.scalars().all())

    async def all(self) -> list[dict[str, str]]:
        """Return all failed jobs as plain dicts."""
        rows = await self.list_all()
        return [
            {
                "uuid": row.uuid,
                "queue": row.queue,
                "payload": row.payload,
                "error": row.error,
            }
            for row in rows
        ]

    async def delete(self, job_uuid: str) -> bool:
        async with self._session_factory() as session, session.begin():
            result = await session.execute(delete(FailedJob).where(FailedJob.uuid == job_uuid))
            deleted_count: int = (
                int(result.rowcount) if result.rowcount is not None else 0  # type: ignore[attr-defined] # ty: ignore[unresolved-attribute]
            )
            return deleted_count > 0

    async def flush(self) -> None:
        async with self._session_factory() as session, session.begin():
            await session.execute(delete(FailedJob))

    async def count(self) -> int:
        from sqlalchemy import func

        async with self._session_factory() as session:
            result = await session.execute(select(func.count()).select_from(FailedJob))
            return result.scalar_one()

    async def close(self) -> None:
        """Release the backing engine (in-memory / test use)."""
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None


__all__ = ["FailedJobStore"]
