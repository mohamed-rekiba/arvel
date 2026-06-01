"""Queue reliability: notifications, DLQ wiring, retry, timeout, backoff, app DB."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import ClassVar

import pytest
from arvel.notifications.notification import Notification
from arvel.queue.config import QueueConfig, QueueDriver
from arvel.queue.drivers.database import DatabaseConnection
from arvel.queue.failed_job_store import FailedJobStore
from arvel.queue.job import Job
from arvel.queue.manager import QueueManager
from arvel.queue.worker import Worker

# ─── Shared fixtures ──────────────────────────────────────────────────────────


async def _make_db_manager() -> tuple[QueueManager, DatabaseConnection]:
    db_conn = DatabaseConnection()
    await db_conn.setup()
    manager = QueueManager(QueueConfig(connection=QueueDriver.DATABASE))
    manager._connections[QueueDriver.DATABASE] = db_conn  # pyright: ignore[reportPrivateUsage]
    return manager, db_conn


async def _make_db_store(db_conn: DatabaseConnection) -> FailedJobStore:
    store = FailedJobStore(session_factory=db_conn._session_factory)  # pyright: ignore[reportPrivateUsage]
    store.set_engine(db_conn._engine)  # pyright: ignore[reportPrivateUsage]
    await store.setup()
    return store


class _TimeoutJob(Job):
    """Job that sleeps forever — used to test timeout enforcement."""

    timeout: int = 1  # 1 second

    async def handle(self) -> None:
        await asyncio.sleep(9999)


class _ImmediateFailJob(Job):
    """Always fails — used to test DLQ and retry semantics."""

    tries: int = 2
    call_count: ClassVar[int] = 0

    async def handle(self) -> None:
        _ImmediateFailJob.call_count += 1
        raise RuntimeError("intentional")

    @classmethod
    def reset(cls) -> None:
        cls.call_count = 0


class _QueuedNotifiable:
    rows: ClassVar[dict[int, _QueuedNotifiable]] = {}
    find_calls: ClassVar[list[int | str]] = []

    def __init__(self, id: int, source: str) -> None:
        self.id = id
        self.source = source

    @classmethod
    async def find(cls, notifiable_id: int | str) -> _QueuedNotifiable | None:
        cls.find_calls.append(notifiable_id)
        return cls.rows.get(int(notifiable_id))


class _QueuedNotification(Notification):
    def via(self, notifiable: object) -> list[str]:
        return ["capture"]


class _CaptureChannel:
    def __init__(self) -> None:
        self.sent: list[object] = []

    async def send(self, notifiable: object, notification: Notification) -> None:
        self.sent.append(notifiable)


# ─── NotificationJob module must exist ───────────────────────────────────────


class TestStory4NotificationJob:
    """arvel.notifications.notification_job.NotificationJob must exist."""

    def test_notification_job_module_importable(self) -> None:
        """Currently FAILS with ImportError (module does not exist)."""
        import arvel.notifications.notification_job as _mod

        assert hasattr(_mod, "NotificationJob"), "NotificationJob class must exist"

    def test_notification_job_is_a_job(self) -> None:
        """NotificationJob must subclass Job."""
        from arvel.notifications.notification_job import NotificationJob

        assert issubclass(NotificationJob, Job)

    def test_notification_job_has_required_fields(self) -> None:
        """Must have notifiable_id, notifiable_class, notification_class fields."""
        from arvel.notifications.notification_job import NotificationJob

        fields = NotificationJob.model_fields
        assert "notifiable_id" in fields
        assert "notifiable_class" in fields
        assert "notification_class" in fields

    @pytest.mark.asyncio
    async def test_notification_job_refetches_notifiable_before_delivery(self) -> None:
        """Queued notifications must not trust notifiable state from the queue payload."""
        from arvel.container import Container
        from arvel.facades.notification import Notification as NotificationFacade
        from arvel.notifications.manager import NotificationManager
        from arvel.notifications.notification_job import NotificationJob

        _QueuedNotifiable.find_calls = []
        _QueuedNotifiable.rows = {7: _QueuedNotifiable(id=7, source="database")}
        channel = _CaptureChannel()
        manager = NotificationManager(Container())
        manager.register_channel("capture", channel)
        NotificationFacade.bind(manager)

        try:
            job = NotificationJob(
                notifiable_id="7",
                notifiable_class=f"{_QueuedNotifiable.__module__}.{_QueuedNotifiable.__qualname__}",
                notification_class=f"{_QueuedNotification.__module__}.{_QueuedNotification.__qualname__}",
            )
            await job.handle()
        finally:
            NotificationFacade.reset()

        assert _QueuedNotifiable.find_calls == [7]
        assert channel.sent == [_QueuedNotifiable.rows[7]]


# ─── QueueWorkCommand must wire FailedJobStore ────────────────────────────────


class TestStory5FailedJobStoreWiring:
    """queue:work must pass FailedJobStore to Worker."""

    @pytest.mark.asyncio
    async def test_exhausted_jobs_land_in_dlq(self) -> None:
        """Jobs that exhaust tries must appear in failed_jobs.

        Currently FAILS because Worker is built without failed_job_store.
        """
        _ImmediateFailJob.reset()
        manager, db_conn = await _make_db_manager()
        store = await _make_db_store(db_conn)

        # Dispatch one failing job
        from arvel.queue.bus import Bus

        bus = Bus(manager)
        job = _ImmediateFailJob()
        job.tries = 2
        await bus.dispatch(job)

        # Worker WITH store (this is how queue:work SHOULD behave)
        worker = Worker(manager, failed_job_store=store)
        await worker.drain_then_stop(poll_timeout=0.1)

        # After exhausting retries, job must be in failed_jobs
        failed = await store.all()
        assert len(failed) == 1
        assert "intentional" in failed[0]["error"]

    @pytest.mark.asyncio
    async def test_queue_work_command_injects_failed_job_store(self) -> None:
        """QueueWorkCommand.run_worker must create Worker with failed_job_store.

        Currently FAILS: Worker is constructed without failed_job_store=...
        """
        from arvel.queue.commands.queue_work import QueueWorkCommand

        manager, db_conn = await _make_db_manager()
        store = await _make_db_store(db_conn)

        # The command must accept and forward a FailedJobStore.
        # If QueueWorkCommand doesn't support this, constructing it will fail.
        # After fix: QueueWorkCommand resolves FailedJobStore from the container.
        cmd = QueueWorkCommand(manager, failed_job_store=store)
        assert cmd is not None


# ─── queue:retry must reset attempts=0 ──────────────────────────────────────


class TestStory6RetryResetsAttempts:
    """retry must explicitly set envelope.attempts = 0."""

    @pytest.mark.asyncio
    async def test_retry_dispatches_with_zero_attempts(self) -> None:
        """Retried envelope must have attempts=0 (full retry budget restored)."""
        from arvel.queue.commands.queue_retry import QueueRetryCommand

        manager, db_conn = await _make_db_manager()
        store = await _make_db_store(db_conn)

        # Create a failed job record with attempts=3 (exhausted)
        job = _ImmediateFailJob()
        envelope = job.to_envelope()
        envelope.attempts = 3
        await store.create(envelope=envelope, queue="default", error="boom")

        failed = await store.all()
        assert len(failed) == 1
        uuid = failed[0]["uuid"]

        # Retry: re-dispatch with attempts=0
        cmd = QueueRetryCommand(manager, store)
        await cmd.retry(uuid)

        # The re-dispatched envelope must have attempts=0
        conn = manager.connection()
        re_envelope = await conn.pop_blocking(queue="default", timeout=0.1)
        assert re_envelope is not None
        assert re_envelope.attempts == 0

    @pytest.mark.asyncio
    async def test_retry_all_dispatches_every_failed_job_with_zero_attempts(self) -> None:
        from arvel.queue.commands.queue_retry import QueueRetryCommand

        manager, db_conn = await _make_db_manager()
        store = await _make_db_store(db_conn)

        for attempts in (3, 4):
            job = _ImmediateFailJob()
            envelope = job.to_envelope()
            envelope.attempts = attempts
            await store.create(envelope=envelope, queue="default", error="boom")

        cmd = QueueRetryCommand(manager, store)
        retried = await cmd.retry_all()

        assert retried == 2
        assert await store.count() == 0

        conn = manager.connection()
        first = await conn.pop_blocking(queue="default", timeout=0.1)
        second = await conn.pop_blocking(queue="default", timeout=0.1)
        assert first is not None
        assert second is not None
        assert [first.attempts, second.attempts] == [0, 0]


# ─── Job timeout enforcement ────────────────────────────────────────────────


class TestStory7JobTimeout:
    """Worker must cancel jobs that exceed Job.timeout."""

    @pytest.mark.asyncio
    async def test_timeout_causes_job_to_fail(self) -> None:
        """Job that runs longer than timeout must be treated as failed.

        Currently FAILS: asyncio.wait_for is not used; job runs forever.
        """
        manager, db_conn = await _make_db_manager()
        store = await _make_db_store(db_conn)

        from arvel.queue.bus import Bus

        bus = Bus(manager)
        await bus.dispatch(_TimeoutJob())

        worker = Worker(manager, failed_job_store=store)

        # Use a short overall timeout so the test doesn't hang
        async def _run_once() -> None:
            await worker.drain_then_stop(poll_timeout=0.1)

        # With timeout enforcement, this should complete in ~1s (job.timeout=1)
        # Without timeout enforcement, this hangs forever.
        await asyncio.wait_for(_run_once(), timeout=5.0)

        # After timeout, the job must be dead (either retried or in DLQ)
        assert worker.jobs_dead + worker.jobs_retried > 0

    @pytest.mark.asyncio
    async def test_timeout_zero_means_no_timeout(self) -> None:
        """timeout=0 must mean unlimited — job runs to completion normally."""

        class _FastJob(Job):
            timeout: int = 0
            done: ClassVar[bool] = False

            async def handle(self) -> None:
                await asyncio.sleep(0)
                _FastJob.done = True

        _FastJob.done = False
        manager, _ = await _make_db_manager()

        from arvel.queue.bus import Bus

        bus = Bus(manager)
        await bus.dispatch(_FastJob())

        worker = Worker(manager)
        await asyncio.wait_for(worker.drain_then_stop(poll_timeout=0.1), timeout=3.0)

        assert _FastJob.done is True

    @pytest.mark.asyncio
    async def test_timeout_logs_job_class_and_timeout(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, object] = {}

        class _Logger:
            def warning(self, message: str, **context: object) -> None:
                captured["message"] = message
                captured.update(context)

        from arvel.queue import worker as worker_mod

        monkeypatch.setattr(worker_mod, "logger", _Logger())
        manager, _ = await _make_db_manager()

        from arvel.queue.bus import Bus

        bus = Bus(manager)
        job = _TimeoutJob()
        job.tries = 1
        await bus.dispatch(job)

        worker = Worker(manager)
        await asyncio.wait_for(worker.drain_then_stop(poll_timeout=0.1), timeout=3.0)

        assert captured["message"] == "queue.job.timeout"
        job_class = captured["job_class"]
        assert isinstance(job_class, str)
        assert job_class.endswith("_TimeoutJob")
        assert captured["timeout_seconds"] == 1


# ─── Job backoff ──────────────────────────────────────────────────────────────


class TestStory8JobBackoff:
    """Job must support backoff: int | list[int] and retry_until."""

    def test_job_has_backoff_attribute(self) -> None:
        """Job base class must have backoff: int | list[int] = 0.

        Currently FAILS: Job has no backoff attribute.
        """
        assert hasattr(Job, "backoff") or "backoff" in Job.model_fields

    def test_job_has_retry_until_attribute(self) -> None:
        """Job base class must have retry_until: datetime | None = None."""
        assert hasattr(Job, "retry_until") or "retry_until" in Job.model_fields

    def test_job_default_backoff_is_zero(self) -> None:
        """Default backoff value must be 0 (no delay)."""

        class _BackoffJob(Job):
            async def handle(self) -> None:
                pass

        job = _BackoffJob()
        assert job.backoff == 0

    @pytest.mark.asyncio
    async def test_worker_applies_backoff_delay_on_retry(self) -> None:
        """Worker must set envelope.delay from backoff before re-queuing.

        Currently FAILS: envelope.delay is always set to 0 on retry.
        """

        class _BackoffFailJob(Job):
            backoff: int | list[int] = 10
            tries: int = 2
            call_count: ClassVar[int] = 0

            async def handle(self) -> None:
                _BackoffFailJob.call_count += 1
                raise RuntimeError("fail")

        _BackoffFailJob.call_count = 0
        manager, db_conn = await _make_db_manager()

        from arvel.queue.bus import Bus

        bus = Bus(manager)
        await bus.dispatch(_BackoffFailJob())

        # Patch: run one attempt, then inspect the re-queued envelope's delay
        conn = manager.connection()
        envelope = await conn.pop_blocking(queue="default", timeout=0.1)
        assert envelope is not None

        worker = Worker(manager)
        await worker._process_one(envelope)  # pyright: ignore[reportPrivateUsage]

        # The job was re-queued (not sent to DLQ)
        assert worker._jobs_retried == 1  # pyright: ignore[reportPrivateUsage]
        assert worker._jobs_dead == 0  # pyright: ignore[reportPrivateUsage]

        # The re-queued row must have available_at roughly 10 seconds ahead.
        # We query the DB directly because pop_blocking filters out delayed jobs.
        import time as _time

        from arvel.queue.drivers.database import JobRow  # pyright: ignore[reportPrivateUsage]
        from sqlalchemy import select as _select

        async with db_conn._session_factory() as session:  # pyright: ignore[reportPrivateUsage]
            result = await session.execute(_select(JobRow).where(JobRow.queue == "default"))
            row = result.scalar_one_or_none()
        assert row is not None
        # available_at should be at least 9 seconds from now (backoff=10)
        assert row.available_at >= _time.time() + 9

    @pytest.mark.asyncio
    async def test_worker_respects_retry_until_expiry(self) -> None:
        """Jobs past retry_until must be routed to DLQ immediately.

        Currently FAILS: retry_until is not checked.
        """

        class _ExpiredJob(Job):
            retry_until: datetime | None = datetime.now(UTC) - timedelta(seconds=1)
            tries: int = 5
            call_count: ClassVar[int] = 0

            async def handle(self) -> None:
                _ExpiredJob.call_count += 1
                raise RuntimeError("always fails")

        _ExpiredJob.call_count = 0
        manager, db_conn = await _make_db_manager()
        store = await _make_db_store(db_conn)

        from arvel.queue.bus import Bus

        bus = Bus(manager)
        await bus.dispatch(_ExpiredJob())

        worker = Worker(manager, failed_job_store=store)
        await asyncio.wait_for(worker.drain_then_stop(poll_timeout=0.1), timeout=5.0)

        # Even with tries=5, the job must land in DLQ immediately (retry_until expired)
        failed = await store.all()
        assert len(failed) == 1
        # The job should have run at most once (no retries after retry_until)
        assert _ExpiredJob.call_count <= 1


# ─── Database queue uses configured app DB ──────────────────────────────────


class TestStory9DatabaseQueueConfiguredDatabase:
    @pytest.mark.asyncio
    async def test_database_queue_reuses_bound_app_session_factory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from arvel import Application
        from arvel.queue.drivers.database import DatabaseConnection, JobRow
        from arvel.queue.envelope import JobEnvelope
        from arvel.queue.manager import QueueManager
        from arvel.queue.providers.queue_service_provider import QueueServiceProvider
        from sqlalchemy import func, select
        from sqlalchemy.ext.asyncio import (
            AsyncEngine,
            AsyncSession,
            async_sessionmaker,
            create_async_engine,
        )

        db_path = tmp_path / "queue.sqlite"
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
        factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            engine, expire_on_commit=False
        )
        app = Application()
        app.container.instance(AsyncEngine, engine)
        app.container.instance(async_sessionmaker, factory)
        monkeypatch.setenv("QUEUE_CONNECTION", "database")

        try:
            provider = QueueServiceProvider(app)
            provider.register()
            manager = app.container.make(QueueManager)
            connection = manager.connection()

            assert isinstance(connection, DatabaseConnection)
            assert connection.engine is engine
            assert connection.session_factory is factory

            await connection.setup()
            await connection.push(JobEnvelope(job_class="tests.jobs.Example", payload={}))

            async with factory() as session:
                result = await session.execute(select(func.count()).select_from(JobRow))
                assert result.scalar_one() == 1
        finally:
            await engine.dispose()

    def test_database_pop_query_uses_skip_locked_for_postgres(self) -> None:
        from arvel.queue.drivers.database import build_pop_statement
        from sqlalchemy.dialects import postgresql
        from sqlalchemy.engine.interfaces import Dialect

        statement = build_pop_statement(queue="default", now=123)
        dialect_cls: type[Dialect] = postgresql.dialect
        sql = str(statement.compile(dialect=dialect_cls()))

        assert "FOR UPDATE SKIP LOCKED" in sql
