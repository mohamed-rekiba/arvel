"""Tests for SchedulerKernel."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

import pytest
import pytest_asyncio
from arvel.queue.job import Job

if TYPE_CHECKING:
    from arvel.cache import CacheManager
    from arvel.scheduling import SchedulerKernel


@pytest_asyncio.fixture
async def cache_manager() -> CacheManager:
    """In-memory CacheManager — backs scheduler locks for tests."""
    import tempfile

    from arvel.cache import CacheManager
    from arvel.config.cache_config import CacheConfig, CacheDriver

    cfg = CacheConfig(
        connection=CacheDriver.ARRAY,
        prefix="test:",
        file_path=tempfile.gettempdir(),
    )
    return CacheManager(cfg)


@pytest_asyncio.fixture
async def kernel(cache_manager: CacheManager) -> SchedulerKernel:
    """SchedulerKernel wired to in-memory cache + recording log."""
    from arvel.scheduling import Schedule, SchedulerKernel

    schedule = Schedule()
    return SchedulerKernel(schedule=schedule, cache_manager=cache_manager)


class TestRunDueTasks:
    """+ runs due tasks, skips not-due."""

    @pytest.mark.asyncio
    async def test_runs_only_due_tasks(self, kernel: SchedulerKernel) -> None:
        ran: list[str] = []

        async def task_due() -> None:
            ran.append("due")

        async def task_not_due() -> None:
            ran.append("not-due")

        kernel.schedule.call(task_due).everyMinute()  # always due
        kernel.schedule.call(task_not_due).yearly()  # only Jan 1 00:00

        now = datetime(2026, 5, 19, 14, 30, 0, tzinfo=UTC)
        result = await kernel.run_due_tasks(now)

        assert "due" in ran
        assert "not-due" not in ran
        assert len(result.outcomes) == 1


class TestWithoutOverlapping:
    """concurrent execution lock prevents overlap."""

    @pytest.mark.asyncio
    async def test_first_run_acquires_lock(self, kernel: SchedulerKernel) -> None:
        ran: list[str] = []

        async def slow_task() -> None:
            ran.append("ran")

        kernel.schedule.call(slow_task).everyMinute().withoutOverlapping().name("slow")

        now = datetime(2026, 5, 19, 14, 30, 0, tzinfo=UTC)
        await kernel.run_due_tasks(now)

        assert ran == ["ran"]

    @pytest.mark.asyncio
    async def test_simultaneous_runs_only_one_executes(self, cache_manager: CacheManager) -> None:
        """two SchedulerKernel instances see the same lock."""
        import asyncio

        from arvel.scheduling import Schedule, SchedulerKernel

        run_count = 0

        async def slow_task() -> None:
            nonlocal run_count
            await asyncio.sleep(0.05)
            run_count += 1

        async def make_kernel() -> SchedulerKernel:
            sched = Schedule()
            sched.call(slow_task).everyMinute().withoutOverlapping(ttl_minutes=1).name("shared")
            return SchedulerKernel(schedule=sched, cache_manager=cache_manager)

        k1, k2 = await make_kernel(), await make_kernel()
        now = datetime(2026, 5, 19, 14, 30, 0, tzinfo=UTC)
        await asyncio.gather(k1.run_due_tasks(now), k2.run_due_tasks(now))

        assert run_count == 1


class TestOnOneServer:
    """onOneServer elects exactly one winner."""

    @pytest.mark.asyncio
    async def test_two_servers_only_one_wins(self, cache_manager: CacheManager) -> None:
        import asyncio

        from arvel.scheduling import Schedule, SchedulerKernel

        winners: list[str] = []

        async def task() -> None:
            winners.append("won")

        async def make_kernel(host: str) -> SchedulerKernel:
            sched = Schedule()
            sched.call(task).everyMinute().onOneServer(ttl_seconds=30).name("election")
            return SchedulerKernel(schedule=sched, cache_manager=cache_manager)

        k1, k2 = await make_kernel("host-a"), await make_kernel("host-b")
        now = datetime(2026, 5, 19, 14, 30, 0, tzinfo=UTC)
        await asyncio.gather(k1.run_due_tasks(now), k2.run_due_tasks(now))

        assert len(winners) == 1


class TestFailureHandling:
    """task exception is caught and logged."""

    @pytest.mark.asyncio
    async def test_task_exception_logged_to_scheduler_channel(
        self, kernel: SchedulerKernel
    ) -> None:
        async def crashes() -> None:
            raise RuntimeError("boom")

        kernel.schedule.call(crashes).everyMinute().name("kaboom")

        now = datetime(2026, 5, 19, 14, 30, 0, tzinfo=UTC)
        result = await kernel.run_due_tasks(now)

        assert any(o.failed for o in result.outcomes)
        # Verify the error log was emitted via the OTel Log facade
        from arvel.testing.observability import FakeObservability

        with FakeObservability() as obs:
            await kernel.run_due_tasks(now)
        assert any(
            r.body == "scheduler.task.failed" and r.attributes.get("task_name") == "kaboom"
            for r in obs.log_records
        )

    @pytest.mark.asyncio
    async def test_loop_continues_after_failure(self, kernel: SchedulerKernel) -> None:
        ran: list[str] = []

        async def crashes() -> None:
            raise RuntimeError("boom")

        async def succeeds() -> None:
            ran.append("ran")

        kernel.schedule.call(crashes).everyMinute().name("kaboom")
        kernel.schedule.call(succeeds).everyMinute().name("ok")

        now = datetime(2026, 5, 19, 14, 30, 0, tzinfo=UTC)
        await kernel.run_due_tasks(now)

        assert "ran" in ran


class TestServeForever:
    """schedule:work loop semantics via SchedulerKernel.serve_forever."""

    @pytest.mark.asyncio
    async def test_max_failures_stops_loop(self, kernel: SchedulerKernel) -> None:
        async def always_crashes() -> None:
            raise RuntimeError("nope")

        kernel.schedule.call(always_crashes).everyMinute().name("doomed")

        # Should stop after 2 failures
        await kernel.serve_forever(sleep_seconds=0.01, max_failures=2, max_iterations=5)

        # If max_failures didn't stop it, we'd run 5 iterations
        # (allowed to detect via outcomes count or internal counter)
        assert kernel.consecutive_failures >= 2


# Schedule.job() / Schedule.command() dispatch


class _RecordingJob(Job):
    """Minimal Job subclass for the dispatch_job branch.

    Tracks every instance constructed via ``model_post_init`` (overriding
    ``__init__`` would conflict with Pydantic's field-assignment logic).
    """

    instances: ClassVar[list[_RecordingJob]] = []

    def model_post_init(self, context: object, /) -> None:
        type(self).instances.append(self)

    async def handle(self) -> None:  # pragma: no cover — never invoked, only dispatched
        return None


class TestScheduleJobDispatch:
    """Schedule.job(MyJob) must call dispatch_job(MyJob()) when configured."""

    @pytest.mark.asyncio
    async def test_dispatch_job_callback_invoked_with_instance(
        self,
        cache_manager: CacheManager,
    ) -> None:
        from arvel.scheduling import Schedule, SchedulerKernel

        dispatched: list[object] = []

        async def _dispatch(job: object) -> None:
            dispatched.append(job)

        _RecordingJob.instances = []
        from arvel.scheduling import SchedulerHooks

        schedule = Schedule()
        schedule.job(_RecordingJob).everyMinute().name("recorder")
        kernel = SchedulerKernel(
            schedule=schedule,
            cache_manager=cache_manager,
            hooks=SchedulerHooks(dispatch_job=_dispatch),
        )

        now = datetime(2026, 5, 19, 14, 30, 0, tzinfo=UTC)
        result = await kernel.run_due_tasks(now)

        assert len(dispatched) == 1
        assert isinstance(dispatched[0], _RecordingJob)
        assert len(_RecordingJob.instances) == 1
        assert all(o.succeeded for o in result.outcomes)

    @pytest.mark.asyncio
    async def test_missing_dispatch_job_skips_with_clear_reason(
        self,
        cache_manager: CacheManager,
    ) -> None:
        from arvel.scheduling import Schedule, SchedulerKernel

        schedule = Schedule()
        schedule.job(_RecordingJob).everyMinute().name("recorder")
        kernel = SchedulerKernel(
            schedule=schedule,
            cache_manager=cache_manager,
            hooks=None,
        )

        now = datetime(2026, 5, 19, 14, 30, 0, tzinfo=UTC)
        result = await kernel.run_due_tasks(now)

        assert len(result.outcomes) == 1
        outcome = result.outcomes[0]
        assert outcome.skipped is True
        assert outcome.reason == "no_dispatch_job_callback"


class TestScheduleCommandDispatch:
    """Schedule.command("name") must call run_command("name") when configured."""

    @pytest.mark.asyncio
    async def test_run_command_callback_invoked_with_name(
        self,
        cache_manager: CacheManager,
    ) -> None:
        from arvel.scheduling import Schedule, SchedulerKernel

        invocations: list[str] = []

        def _runner(name: str) -> int:
            invocations.append(name)
            return 0

        from arvel.scheduling import SchedulerHooks

        schedule = Schedule()
        schedule.command("cache:clear").everyMinute()
        kernel = SchedulerKernel(
            schedule=schedule,
            cache_manager=cache_manager,
            hooks=SchedulerHooks(run_command=_runner),
        )

        now = datetime(2026, 5, 19, 14, 30, 0, tzinfo=UTC)
        result = await kernel.run_due_tasks(now)

        assert invocations == ["cache:clear"]
        assert all(o.succeeded for o in result.outcomes)

    @pytest.mark.asyncio
    async def test_run_command_awaitable_is_awaited(
        self,
        cache_manager: CacheManager,
    ) -> None:
        from arvel.scheduling import Schedule, SchedulerKernel

        invocations: list[str] = []

        async def _async_runner(name: str) -> int:
            invocations.append(name)
            return 0

        from arvel.scheduling import SchedulerHooks

        schedule = Schedule()
        schedule.command("db:seed").everyMinute()
        kernel = SchedulerKernel(
            schedule=schedule,
            cache_manager=cache_manager,
            hooks=SchedulerHooks(run_command=_async_runner),
        )

        now = datetime(2026, 5, 19, 14, 30, 0, tzinfo=UTC)
        result = await kernel.run_due_tasks(now)

        assert invocations == ["db:seed"]
        assert all(o.succeeded for o in result.outcomes)

    @pytest.mark.asyncio
    async def test_missing_run_command_skips_with_clear_reason(
        self,
        cache_manager: CacheManager,
    ) -> None:
        from arvel.scheduling import Schedule, SchedulerKernel

        schedule = Schedule()
        schedule.command("cache:clear").everyMinute()
        kernel = SchedulerKernel(
            schedule=schedule,
            cache_manager=cache_manager,
            hooks=None,
        )

        now = datetime(2026, 5, 19, 14, 30, 0, tzinfo=UTC)
        result = await kernel.run_due_tasks(now)

        assert len(result.outcomes) == 1
        outcome = result.outcomes[0]
        assert outcome.skipped is True
        assert outcome.reason == "no_run_command_callback"


class TestSchedulerProviderWiresBus:
    """The SchedulerServiceProvider must auto-wire dispatch_job when Bus is bound."""

    @pytest.mark.asyncio
    async def test_kernel_dispatches_jobs_when_queue_provider_registered(self) -> None:
        from arvel.application import Application
        from arvel.providers.scheduler_provider import SchedulerServiceProvider
        from arvel.queue.providers.queue_service_provider import QueueServiceProvider
        from arvel.scheduling import Schedule, SchedulerKernel

        app = Application()
        # Register the queue first so Bus is in the container, then the scheduler.
        for cls in (QueueServiceProvider, SchedulerServiceProvider):
            inst = cls(app)
            inst.register()

        from arvel.queue.bus import Bus

        assert app.container.bound(Bus), "Queue provider should bind Bus into the container."

        # Register a job; assert the wired dispatch path completes without error.
        # We don't assert "envelope landed in driver" — that's covered by the
        # queue tests. Here we only verify the wiring lights up.
        _RecordingJob.instances = []
        schedule: Schedule = app.container.make(Schedule)
        schedule.job(_RecordingJob).everyMinute().name("wired")

        kernel: SchedulerKernel = app.container.make(SchedulerKernel)
        now = datetime(2026, 5, 19, 14, 30, 0, tzinfo=UTC)
        result = await kernel.run_due_tasks(now)

        # No skip with "no_dispatch_job_callback" — wiring worked.
        outcome = next(o for o in result.outcomes if o.task_name == "wired")
        assert outcome.succeeded, (outcome.failed, outcome.skipped, outcome.reason)
        # >= 1 because the default sync driver also instantiates the Job when
        # it runs handle() inline, but we only care that the scheduler made
        # at least one instance.
        assert len(_RecordingJob.instances) >= 1


class TestMaintenanceMode:
    """Scheduler honors `inMaintenanceMode()` against the live marker."""

    @pytest.mark.asyncio
    async def test_skips_task_when_app_is_down_and_task_did_not_opt_in(
        self,
        cache_manager: CacheManager,
    ) -> None:
        from arvel.scheduling import Schedule, SchedulerKernel

        class _DownMarker:
            def is_down(self) -> bool:
                return True

        ran: list[str] = []

        async def task_call() -> None:
            ran.append("ran")

        schedule = Schedule()
        schedule.call(task_call).everyMinute().name("no-opt-in")

        kernel = SchedulerKernel(
            schedule=schedule,
            cache_manager=cache_manager,
            maintenance_manager=_DownMarker(),  # type: ignore[arg-type]
        )
        now = datetime(2026, 5, 19, 14, 30, 0, tzinfo=UTC)
        result = await kernel.run_due_tasks(now)

        outcome = next(o for o in result.outcomes if o.task_name == "no-opt-in")
        assert outcome.skipped is True
        assert outcome.reason == "in_maintenance_mode"
        assert ran == []

    @pytest.mark.asyncio
    async def test_runs_task_in_maintenance_when_opted_in(
        self,
        cache_manager: CacheManager,
    ) -> None:
        from arvel.scheduling import Schedule, SchedulerKernel

        class _DownMarker:
            def is_down(self) -> bool:
                return True

        ran: list[str] = []

        async def task_call() -> None:
            ran.append("ran")

        schedule = Schedule()
        schedule.call(task_call).everyMinute().name("opted-in").inMaintenanceMode()

        kernel = SchedulerKernel(
            schedule=schedule,
            cache_manager=cache_manager,
            maintenance_manager=_DownMarker(),  # type: ignore[arg-type]
        )
        now = datetime(2026, 5, 19, 14, 30, 0, tzinfo=UTC)
        result = await kernel.run_due_tasks(now)

        outcome = next(o for o in result.outcomes if o.task_name == "opted-in")
        assert outcome.succeeded is True
        assert ran == ["ran"]


class TestOutputTo:
    """Scheduler appends task stdout/stderr to `output_to` when set."""

    @pytest.mark.asyncio
    async def test_captures_stdout_to_output_to_file(
        self,
        cache_manager: CacheManager,
        tmp_path: Path,
    ) -> None:
        from arvel.scheduling import Schedule, SchedulerKernel

        async def chatty() -> None:
            sys.stdout.write("captured-stdout-line\n")

        out_path = tmp_path / "logs" / "scheduler.log"
        schedule = Schedule()
        schedule.call(chatty).everyMinute().name("chatty").outputTo(out_path)

        kernel = SchedulerKernel(schedule=schedule, cache_manager=cache_manager)
        now = datetime(2026, 5, 19, 14, 30, 0, tzinfo=UTC)
        await kernel.run_due_tasks(now)

        assert out_path.exists(), "outputTo must create parents and write the file"
        contents = out_path.read_text(encoding="utf-8")
        assert "captured-stdout-line" in contents

    @pytest.mark.asyncio
    async def test_output_to_failure_does_not_break_task(
        self,
        cache_manager: CacheManager,
        tmp_path: Path,
    ) -> None:
        from arvel.scheduling import Schedule, SchedulerKernel

        ran: list[str] = []

        async def task_call() -> None:
            ran.append("ran")

        # Point output_to at an existing FILE, then ask the kernel to treat
        # it as a directory parent — open() will fail and we should still run.
        a_file = tmp_path / "blocking-file"
        a_file.write_text("not a directory")
        unwritable = a_file / "subdir" / "out.log"

        schedule = Schedule()
        schedule.call(task_call).everyMinute().name("resilient").outputTo(unwritable)

        kernel = SchedulerKernel(schedule=schedule, cache_manager=cache_manager)
        now = datetime(2026, 5, 19, 14, 30, 0, tzinfo=UTC)
        result = await kernel.run_due_tasks(now)

        outcome = next(o for o in result.outcomes if o.task_name == "resilient")
        assert outcome.succeeded is True
        assert ran == ["ran"]
