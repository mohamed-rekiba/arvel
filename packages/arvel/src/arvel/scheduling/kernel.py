"""SchedulerKernel — async dispatch loop with cache-lock-based safety.

 wired the ``job`` and ``command`` callback kinds to actually run.
The kernel stays decoupled from the queue and console subsystems by
accepting two optional callbacks (``dispatch_job``, ``run_command``)
instead of importing ``Bus`` or ``Application`` directly. The default
configuration (no callbacks) preserves the historical skip behavior so
existing apps that only use ``Schedule.call(...)`` are unaffected.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import io
import sys
import traceback
from collections.abc import Awaitable, Callable, Generator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from arvel.cache import CacheManager
    from arvel.maintenance.manager import MaintenanceModeManager
    from arvel.scheduling.schedule import Schedule
    from arvel.scheduling.scheduled_task import ScheduledTask


DispatchJob = Callable[[Any], Awaitable[None]]
"""Hook invoked for ``Schedule.job(MyJob)``. Receives the instantiated Job."""

RunCommand = Callable[[str], Awaitable[int] | int]
"""Hook invoked for ``Schedule.command("name")``. Receives the command name."""


class _Tee(io.TextIOBase):
    """Write to two text streams at once. Used by ``outputTo`` redirection.

    The secondary stream may be closed before the GC finalises this tee (e.g.
    when the redirect block exits before stdout's own buffer is drained). All
    secondary I/O is best-effort and swallows both ``OSError`` and
    ``ValueError`` (the latter is what closed-file flushes raise).
    """

    def __init__(self, primary: Any, secondary: Any) -> None:
        self._primary = primary
        self._secondary = secondary

    def write(self, s: str) -> int:
        with contextlib.suppress(OSError, ValueError):
            self._secondary.write(s)
        return int(self._primary.write(s))

    def flush(self) -> None:
        with contextlib.suppress(OSError, ValueError):
            self._secondary.flush()
        with contextlib.suppress(OSError, ValueError):
            self._primary.flush()


@dataclass(frozen=True)
class SchedulerHooks:
    """Optional dispatch hooks injected at kernel construction time.

    Both fields default to ``None`` so existing callers that only use
    ``Schedule.call(...)`` don't have to opt in.
    """

    dispatch_job: DispatchJob | None = None
    run_command: RunCommand | None = None


@dataclass(frozen=True)
class TaskOutcome:
    """Result of running a single scheduled task."""

    task_name: str
    succeeded: bool
    failed: bool
    skipped: bool = False
    reason: str | None = None

    @classmethod
    def success(cls, name: str) -> TaskOutcome:
        return cls(task_name=name, succeeded=True, failed=False)

    @classmethod
    def failure(cls, name: str, reason: str) -> TaskOutcome:
        return cls(task_name=name, succeeded=False, failed=True, reason=reason)

    @classmethod
    def skip(cls, name: str, reason: str) -> TaskOutcome:
        return cls(task_name=name, succeeded=False, failed=False, skipped=True, reason=reason)


@dataclass(frozen=True)
class SchedulerRunResult:
    """Result of one run_due_tasks tick."""

    outcomes: tuple[TaskOutcome, ...]
    evaluated_at: datetime


class SchedulerKernel:
    """Async dispatch loop. One instance per process."""

    def __init__(
        self,
        schedule: Schedule,
        cache_manager: CacheManager | None = None,
        *,
        max_concurrency: int = 16,
        hooks: SchedulerHooks | None = None,
        maintenance_manager: MaintenanceModeManager | None = None,
    ) -> None:
        self.schedule = schedule
        self._cache = cache_manager
        self._sem = asyncio.Semaphore(max_concurrency)
        self.hooks = hooks or SchedulerHooks()
        self.consecutive_failures = 0
        self._maintenance_manager = maintenance_manager

    async def run_due_tasks(self, now: datetime) -> SchedulerRunResult:
        """Evaluate registered tasks against ``now`` and dispatch the due ones.

        Uses asyncio.TaskGroup for structured concurrency.
        Per-task exceptions are caught BEFORE the TaskGroup boundary so a
        single failing task never cancels its siblings.
        """
        due = [t for t in self.schedule.tasks() if t.is_due(now)]
        outcomes: list[TaskOutcome] = []

        if not due:
            return SchedulerRunResult(outcomes=(), evaluated_at=now)

        async with asyncio.TaskGroup() as tg:
            for task in due:
                tg.create_task(self._run_one(task, outcomes, now))

        if any(o.failed for o in outcomes):
            self.consecutive_failures += 1
        else:
            self.consecutive_failures = 0

        return SchedulerRunResult(outcomes=tuple(outcomes), evaluated_at=now)

    async def serve_forever(
        self,
        *,
        sleep_seconds: float = 60.0,
        max_failures: int | None = None,
        max_iterations: int | None = None,
    ) -> None:
        """Run a sleep→tick→sleep loop. Exit on max_failures or KeyboardInterrupt.

        Also responds to cache-marker signals from ``schedule:interrupt``
        (graceful exit at next tick) and ``schedule:pause`` / ``schedule:continue``
        (skip task execution while paused).
        """
        from datetime import UTC

        from arvel.logging.facade import Log
        from arvel.scheduling.signal import SchedulerSignal

        _signal = SchedulerSignal()
        iterations = 0
        try:
            while True:
                iterations += 1

                if await _signal.check_and_clear_interrupt():
                    Log.channel("scheduler").info(
                        "scheduler.loop.stopped", reason="interrupt_signal"
                    )
                    return

                if not await _signal.is_paused():
                    await self.run_due_tasks(datetime.now(UTC))

                if max_failures is not None and self.consecutive_failures >= max_failures:
                    Log.channel("scheduler").error(
                        "scheduler.loop.stopped",
                        reason="max_failures_reached",
                        consecutive_failures=self.consecutive_failures,
                    )
                    return
                if max_iterations is not None and iterations >= max_iterations:
                    return
                await asyncio.sleep(sleep_seconds)
        except (
            KeyboardInterrupt,
            asyncio.CancelledError,
        ):
            from arvel.logging.facade import Log as _Log

            _Log.channel("scheduler").info("scheduler.loop.interrupted")
            raise

    async def _run_one(
        self, task: ScheduledTask, outcomes: list[TaskOutcome], now: datetime
    ) -> None:
        async with self._sem:
            # onOneServer: per-minute election lock. Only the winner runs.
            # The key carries the due minute so it dedupes servers within that
            # minute but rotates afterwards — without the slot a single static
            # key would keep every server blocked for the whole TTL, silently
            # dropping the next runs (Laravel keys it mutexName().format('Hi')).
            if task.on_one_server and self._cache is not None:
                slot = now.strftime("%Y%m%d%H%M")
                lock = self._cache.lock(
                    f"scheduler:onserver:{task.name}:{slot}",
                    ttl=task.on_one_server_ttl_seconds,
                )
                if not await lock.acquire():
                    outcomes.append(TaskOutcome.skip(task.name, "not_one_server_winner"))
                    return

            # withoutOverlapping: long-lived "no concurrent run" guard.
            if task.without_overlapping and self._cache is not None:
                overlap_lock = self._cache.lock(
                    f"scheduler:overlap:{task.name}",
                    ttl=task.without_overlapping_ttl_minutes * 60,
                )
                if not await overlap_lock.acquire():
                    outcomes.append(TaskOutcome.skip(task.name, "still_running"))
                    return
                try:
                    await self._invoke(task, outcomes)
                finally:
                    await overlap_lock.release()
            else:
                await self._invoke(task, outcomes)

    async def _invoke(self, task: ScheduledTask, outcomes: list[TaskOutcome]) -> None:
        # Laravel parity: `.inMaintenanceMode()` opts a task IN to running while
        # the app is down. Tasks that DIDN'T opt in are skipped in maintenance.
        if self._app_in_maintenance() and not task.in_maintenance_mode:
            outcomes.append(TaskOutcome.skip(task.name, "in_maintenance_mode"))
            return
        try:
            if task.callback is None:
                outcomes.append(TaskOutcome.skip(task.name, "no_callback"))
                return
            with self._capture_output(task.output_to):
                if task.callback_kind == "call":
                    await self._invoke_call(task)
                elif task.callback_kind == "job":
                    skip_reason = await self._invoke_job(task)
                    if skip_reason is not None:
                        outcomes.append(TaskOutcome.skip(task.name, skip_reason))
                        return
                elif task.callback_kind == "command":
                    skip_reason = await self._invoke_command(task)
                    if skip_reason is not None:
                        outcomes.append(TaskOutcome.skip(task.name, skip_reason))
                        return
            outcomes.append(TaskOutcome.success(task.name))
        except Exception as e:
            from arvel.logging.facade import Log

            Log.channel("scheduler").error(
                "scheduler.task.failed",
                task_name=task.name,
                exception_type=type(e).__name__,
                traceback=traceback.format_exc(),
            )
            outcomes.append(TaskOutcome.failure(task.name, reason=str(e)))

    def _app_in_maintenance(self) -> bool:
        if self._maintenance_manager is None:
            return False
        try:
            return self._maintenance_manager.is_down()
        except Exception:
            # Best-effort: never let a maintenance-marker read failure crash
            # the scheduler. Log and treat as "not in maintenance".
            from arvel.logging.facade import Log

            Log.channel("scheduler").warning(
                "scheduler.maintenance_check_failed",
                error_type="MaintenanceManagerError",
            )
            return False

    @contextlib.contextmanager
    def _capture_output(self, path: Path | None) -> Generator[None]:
        """Tee stdout/stderr to ``path`` for the duration of the block.

        Best-effort — if the file can't be opened we log a warning and let the
        task run with normal stdio. A successful task whose output redirect
        fails is still a success.
        """
        if path is None:
            yield
            return
        target = Path(path)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            sink = target.open("a", encoding="utf-8")
        except OSError as exc:
            from arvel.logging.facade import Log

            Log.channel("scheduler").warning(
                "scheduler.output_to.open_failed",
                path=str(target),
                error=str(exc),
            )
            yield
            return
        tee_out = _Tee(sys.stdout, sink)
        tee_err = _Tee(sys.stderr, sink)
        with contextlib.redirect_stdout(tee_out), contextlib.redirect_stderr(tee_err):
            try:
                yield
            finally:
                sink.flush()
                sink.close()

    async def _invoke_call(self, task: ScheduledTask) -> None:
        callback = task.callback
        if inspect.iscoroutinefunction(callback):
            await callback()
        elif callable(callback):
            result = callback()
            if inspect.isawaitable(result):
                await result

    async def _invoke_job(self, task: ScheduledTask) -> str | None:
        """Dispatch a Job to the queue. Returns a skip reason or None on success."""
        if self.hooks.dispatch_job is None:
            return "no_dispatch_job_callback"
        job_cls = task.callback
        if not isinstance(job_cls, type):
            raise TypeError(
                f"Schedule.job() expects a class, got {type(job_cls).__name__}",
            )
        job_instance = job_cls()
        await self.hooks.dispatch_job(job_instance)
        return None

    async def _invoke_command(self, task: ScheduledTask) -> str | None:
        """Run a console command by name. Returns a skip reason or None on success."""
        if self.hooks.run_command is None:
            return "no_run_command_callback"
        cmd_name = task.callback
        if not isinstance(cmd_name, str):
            raise TypeError(
                f"Schedule.command() expects a string, got {type(cmd_name).__name__}",
            )
        result = self.hooks.run_command(cmd_name)
        if inspect.isawaitable(result):
            await result
        return None


__all__ = [
    "DispatchJob",
    "RunCommand",
    "SchedulerHooks",
    "SchedulerKernel",
    "SchedulerRunResult",
    "TaskOutcome",
]
