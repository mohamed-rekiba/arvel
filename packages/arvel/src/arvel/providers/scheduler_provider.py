"""SchedulerServiceProvider — registers Schedule + SchedulerKernel + schedule:work CLI."""

from __future__ import annotations

import importlib.util
import shlex
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from arvel.console._subsystem import CliSubsystem
from arvel.providers.service_provider import ServiceProvider

if TYPE_CHECKING:
    from arvel.console import Command
    from arvel.queue.job import Job
    from arvel.scheduling.kernel import DispatchJob, RunCommand


class SchedulerServiceProvider(ServiceProvider):
    """Binds Schedule + SchedulerKernel; auto-discovers app/Console/Kernel.py::schedule()."""

    subsystem: ClassVar[CliSubsystem | None] = CliSubsystem.SCHEDULER

    def register(self) -> None:
        from arvel.cache import CacheManager
        from arvel.maintenance.manager import MaintenanceModeManager
        from arvel.scheduling import Schedule, SchedulerKernel

        c = self.app.container

        def _schedule_factory() -> Schedule:
            return Schedule()

        def _kernel_factory() -> SchedulerKernel:
            from arvel.console import Application as ConsoleApplication
            from arvel.queue.bus import Bus
            from arvel.scheduling import SchedulerHooks

            cache_manager = c.make(CacheManager) if c.bound(CacheManager) else None
            maintenance_manager = (
                c.make(MaintenanceModeManager) if c.bound(MaintenanceModeManager) else None
            )

            # Wire Schedule.job() to actually dispatch via Bus
            # when the queue subsystem is registered. Apps without the queue
            # bound continue to get "skipped: no_dispatch_job_callback".
            dispatch_job_cb: DispatchJob | None = None
            if c.bound(Bus):
                bus = c.make(Bus)

                async def _dispatch(job: Job) -> None:
                    await bus.dispatch(job)

                dispatch_job_cb = _dispatch

            # Wire Schedule.command("name") to invoke the
            # registered console command when ConsoleServiceProvider has bound
            # the Application. Apps without the console provider continue to
            # get "skipped: no_run_command_callback".
            run_command_cb: RunCommand | None = None
            if c.bound(ConsoleApplication):
                console_app = c.make(ConsoleApplication)

                async def _run(command_string: str) -> None:
                    # Laravel parity: command("emails:send --queue=default") carries
                    # flags. Split into name + args and dispatch through Typer so the
                    # command's real (often async) callback runs, not a stub handle().
                    parts = shlex.split(command_string)
                    if not parts:
                        msg = "Scheduled command string is empty"
                        raise RuntimeError(msg)
                    name, args = parts[0], parts[1:]
                    code = await console_app.adispatch(name, args)
                    if code != 0:
                        msg = f"Scheduled command {command_string!r} exited with code {code}"
                        raise RuntimeError(msg)

                run_command_cb = _run

            return SchedulerKernel(
                schedule=c.make(Schedule),
                cache_manager=cache_manager,
                hooks=SchedulerHooks(
                    dispatch_job=dispatch_job_cb,
                    run_command=run_command_cb,
                ),
                maintenance_manager=maintenance_manager,
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
        # No kernel at all is fine — the app just has no schedule.
        if not kernel_file.exists():
            return

        spec = importlib.util.spec_from_file_location("_app_console_kernel", kernel_file)
        if spec is None or spec.loader is None:
            return
        module = importlib.util.module_from_spec(spec)
        # A broken Kernel is a developer error — fail loud (Laravel parity) instead
        # of booting with a silently empty schedule. Import/schedule() errors
        # propagate; only a missing Kernel/schedule is treated as "no schedule".
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
