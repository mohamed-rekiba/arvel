"""Tests for FailedJobStore — FR-008-010..012."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from arvel.queue.envelope import JobEnvelope
from arvel.queue.failed_job_store import FailedJobStore


@pytest_asyncio.fixture
async def failed_store() -> AsyncIterator[FailedJobStore]:
    """Return a FailedJobStore backed by in-memory SQLite."""
    store = FailedJobStore.create_in_memory()
    await store.setup()
    try:
        yield store
    finally:
        await store.close()


class TestFailedJobStore:
    """FR-008-010: Failed jobs are persisted in failed_jobs table."""

    @pytest.mark.asyncio
    async def test_create_failed_job(self, failed_store: FailedJobStore) -> None:
        env = JobEnvelope(job_class="myapp.jobs.MyJob", payload={"value": 1})
        failed = await failed_store.create(
            envelope=env, queue="default", error="RuntimeError: boom"
        )
        assert failed.uuid is not None
        assert failed.queue == "default"

    @pytest.mark.asyncio
    async def test_find_by_uuid(self, failed_store: FailedJobStore) -> None:
        env = JobEnvelope(job_class="myapp.jobs.MyJob", payload={"value": 2})
        created = await failed_store.create(envelope=env, queue="default", error="err")
        found = await failed_store.find(created.uuid)
        assert found is not None
        assert found.uuid == created.uuid

    @pytest.mark.asyncio
    async def test_find_missing_returns_none(self, failed_store: FailedJobStore) -> None:
        result = await failed_store.find("00000000-0000-0000-0000-000000000000")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_all(self, failed_store: FailedJobStore) -> None:
        for i in range(3):
            env = JobEnvelope(job_class="myapp.jobs.MyJob", payload={"value": i})
            await failed_store.create(envelope=env, queue="default", error="err")
        rows = await failed_store.list_all()
        assert len(rows) >= 3

    @pytest.mark.asyncio
    async def test_delete_by_uuid(self, failed_store: FailedJobStore) -> None:
        """FR-008-011: queue:forget deletes a failed job."""
        env = JobEnvelope(job_class="myapp.jobs.MyJob", payload={"value": 3})
        created = await failed_store.create(envelope=env, queue="default", error="err")
        deleted = await failed_store.delete(created.uuid)
        assert deleted is True
        assert await failed_store.find(created.uuid) is None

    @pytest.mark.asyncio
    async def test_delete_missing_returns_false(self, failed_store: FailedJobStore) -> None:
        deleted = await failed_store.delete("00000000-0000-0000-0000-000000000000")
        assert deleted is False

    @pytest.mark.asyncio
    async def test_flush_all(self, failed_store: FailedJobStore) -> None:
        """FR-008-012: queue:flush clears all failed jobs."""
        for i in range(5):
            env = JobEnvelope(job_class="myapp.jobs.MyJob", payload={"value": i})
            await failed_store.create(envelope=env, queue="default", error="err")
        await failed_store.flush()
        assert await failed_store.count() == 0

    @pytest.mark.asyncio
    async def test_error_truncated_to_65535_chars(self, failed_store: FailedJobStore) -> None:
        """Error column is capped at 65 535 chars (see ADR-035 / schema doc)."""
        long_error = "x" * 100_000
        env = JobEnvelope(job_class="myapp.jobs.MyJob", payload={})
        created = await failed_store.create(envelope=env, queue="default", error=long_error)
        found = await failed_store.find(created.uuid)
        assert found is not None
        assert len(found.error) <= 65_535

    @pytest.mark.asyncio
    async def test_uuid_is_unique(self, failed_store: FailedJobStore) -> None:
        env = JobEnvelope(job_class="myapp.jobs.MyJob", payload={})
        a = await failed_store.create(envelope=env, queue="default", error="e")
        b = await failed_store.create(envelope=env, queue="default", error="e")
        assert a.uuid != b.uuid
