"""SchedulerServiceProvider — registers Schedule + SchedulerKernel + schedule:work CLI."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING

from arvel.logging.facade import Log
from arvel.providers.service_provider import ServiceProvider

if TYPE_CHECKING:
    from arvel.console import Command

logger = Log.channel(__name__)


class SchedulerServiceProvider(ServiceProvider):
    """Binds Schedule + SchedulerKernel; auto-discovers app/Console/Kernel.py::schedule()."""

    def register(self) -> None:
        from typing import Any

        from arvel.cache import CacheManager
        from arvel.scheduling import Schedule, SchedulerKernel

        c = self.app.container

        def _schedule_factory() -> Schedule:
            return Schedule()

        def _kernel_factory() -> SchedulerKernel:
            from arvel.console import Application as ConsoleApplication
            from arvel.queue.bus import Bus
            from arvel.scheduling import SchedulerHooks

            cache_manager = c.make(CacheManager) if c.bound(CacheManager) else None

            # WI-019 Gap-A: wire Schedule.job() to actually dispatch via Bus
            # when the queue subsystem is registered. Apps without the queue
            # bound continue to get "skipped: no_dispatch_job_callback".
            dispatch_job_cb: Any = None
            if c.bound(Bus):
                bus = c.make(Bus)

                async def _dispatch(job: Any) -> None:
                    await bus.dispatch(job)

                dispatch_job_cb = _dispatch

            # WI-020 FB-019-001: wire Schedule.command("name") to invoke the
            # registered console command when ConsoleServiceProvider has bound
            # the Application. Apps without the console provider continue to
            # get "skipped: no_run_command_callback".
            run_command_cb: Any = None
            if c.bound(ConsoleApplication):
                console_app = c.make(ConsoleApplication)

                async def _run(name: str) -> None:
                    code = console_app.run(name)
                    if code != 0:
                        msg = f"Scheduled command {name!r} exited with code {code}"
                        raise RuntimeError(msg)

                run_command_cb = _run

            return SchedulerKernel(
                schedule=c.make(Schedule),
                cache_manager=cache_manager,
                hooks=SchedulerHooks(
                    dispatch_job=dispatch_job_cb,
                    run_command=run_command_cb,
                ),
            )

        c.singleton(Schedule, _schedule_factory)
        c.singleton(SchedulerKernel, _kernel_factory)

    async def boot(self) -> None:
        """Auto-discover app/Console/Kernel.py and call its schedule() method."""
        from arvel.application.errors import EnvironmentNotSetError
        from arvel.scheduling import Schedule

        try:
            base = self.app.base_path()
        except EnvironmentNotSetError, AttributeError:
            base = Path()
        kernel_file = base / "app" / "console" / "kernel.py"
        # Both 'console' (snake_case) and 'Console' (PascalCase) accepted
        if not kernel_file.exists():
            kernel_file = base / "app" / "Console" / "Kernel.py"
        if not kernel_file.exists():
            return
        try:
            spec = importlib.util.spec_from_file_location("_app_console_kernel", kernel_file)
            if spec is None or spec.loader is None:
                return
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            cls = getattr(module, "Kernel", None)
            if cls is None:
                return
            instance = cls()
            schedule_method = getattr(instance, "schedule", None)
            if schedule_method is None:
                return
            schedule = self.app.container.make(Schedule)
            schedule_method(schedule)
        except Exception as exc:
            # User-defined Kernel may raise during import; scheduler boot must be
            # tolerant so the rest of the app still starts. Log so failures are
            # observable rather than silently swallowed.
            logger.warning(
                "scheduler_kernel_discovery_failed",
                kernel_file=str(kernel_file),
                error=str(exc),
                error_type=type(exc).__name__,
            )

    def commands(self) -> list[type[Command] | Command]:
        from arvel.console.commands.schedule_commands import (
            ScheduleContinueCommand,
            ScheduleInterruptCommand,
            ScheduleListCommand,
            SchedulePauseCommand,
            ScheduleWorkCommand,
        )

        return [
            ScheduleWorkCommand,
            ScheduleListCommand,
            ScheduleInterruptCommand,
            SchedulePauseCommand,
            ScheduleContinueCommand,
        ]


__all__ = ["SchedulerServiceProvider"]
