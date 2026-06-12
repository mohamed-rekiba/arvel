"""schedule:work + schedule:list CLI commands.

Both commands need the user's :class:`arvel.scheduling.Schedule` (populated by
``app/console/kernel.py::Kernel.schedule``) and a working
:class:`arvel.scheduling.SchedulerKernel`. They declare
``requires = {SCHEDULER, USER_PROVIDERS}`` so the entrypoint boots the
scheduler subsystem and the user's providers, then binds the resulting
``Application`` to ``self.app``. The handle methods resolve ``Schedule`` and
``SchedulerKernel`` from the container; if the user has not registered
either, the command exits with a clear "no scheduler bound" error rather than
silently building an empty schedule.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated, ClassVar

import typer

from arvel.console import Command, Context
from arvel.console import _async as _arvel_async
from arvel.console._subsystem import CliSubsystem
from arvel.console._t import Option as _Option

if TYPE_CHECKING:
    from arvel.scheduling import Schedule, SchedulerKernel


_SCHEDULER_BIND_MSG = (
    "schedule command requires a bound framework Application "
    "(add CliSubsystem.SCHEDULER to requires)"
)


def _resolve_schedule(cmd: Command) -> Schedule:
    from arvel.scheduling import Schedule

    if cmd.app is None:
        raise RuntimeError(_SCHEDULER_BIND_MSG)
    return cmd.app.container.make(Schedule)


def resolve_kernel(cmd: Command) -> SchedulerKernel:
    from arvel.scheduling import SchedulerKernel

    if cmd.app is None:
        raise RuntimeError(_SCHEDULER_BIND_MSG)
    return cmd.app.container.make(SchedulerKernel)


class ScheduleWorkCommand(Command):
    name: ClassVar[str] = "schedule:work"
    help: ClassVar[str] = "Run the scheduler dispatch loop (foreground)."
    requires: ClassVar[frozenset[CliSubsystem]] = frozenset(
        {CliSubsystem.SCHEDULER, CliSubsystem.USER_PROVIDERS}
    )

    def register(self, app: typer.Typer) -> None:
        cmd_self = self

        def _callback(
            once: Annotated[bool, _Option("--once", help="Run one tick and exit")] = False,
            sleep: Annotated[float, _Option("--sleep", help="Seconds between ticks")] = 60.0,
            max_failures: Annotated[
                int,
                _Option("--max-failures", help="Stop after N consecutive failures (0=disabled)"),
            ] = 0,
        ) -> None:
            # Mirror handle()/schedule:list: a missing kernel exits 2 with a clear
            # message instead of escaping as a traceback.
            try:
                kernel = resolve_kernel(cmd_self)
            except Exception as exc:
                typer.echo(f"schedule:work failed to resolve scheduler kernel: {exc}", err=True)
                raise typer.Exit(2) from exc
            _arvel_async.schedule_async(
                run_loop(kernel, once=once, sleep=sleep, max_failures=max_failures or None)
            )

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        try:
            kernel = resolve_kernel(self)
        except Exception as exc:  # noqa: BLE001
            ctx.error(f"schedule:work failed to resolve scheduler kernel: {exc}")
            return 2
        _arvel_async.schedule_async(kernel.run_due_tasks(datetime.now(UTC)))
        return 0


class ScheduleListCommand(Command):
    name: ClassVar[str] = "schedule:list"
    help: ClassVar[str] = "List registered scheduled tasks."
    requires: ClassVar[frozenset[CliSubsystem]] = frozenset(
        {CliSubsystem.SCHEDULER, CliSubsystem.USER_PROVIDERS}
    )

    def register(self, app: typer.Typer) -> None:
        cmd_self = self

        def _callback() -> None:
            code = cmd_self.handle(Context())
            if code != 0:
                raise typer.Exit(code)

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        try:
            schedule = _resolve_schedule(self)
        except Exception as exc:  # noqa: BLE001
            ctx.error(f"schedule:list failed to resolve user Schedule: {exc}")
            return 2

        tasks = schedule.tasks()
        if not tasks:
            ctx.info("No scheduled tasks registered.")
            return 0
        for task in tasks:
            ctx.info(f"{task.name:40s}  {task.expression:20s}  tz={task.timezone}")
        return 0


async def run_loop(
    kernel: SchedulerKernel, *, once: bool, sleep: float, max_failures: int | None
) -> None:
    if once:
        await kernel.run_due_tasks(datetime.now(UTC))
        return
    await kernel.serve_forever(sleep_seconds=sleep, max_failures=max_failures)
    # serve_forever returns cleanly on interrupt, but also when it gives up after
    # --max-failures. Surface the give-up as a non-zero exit so a supervisor
    # restarts/alerts instead of treating the dead loop as a clean shutdown.
    if max_failures is not None and kernel.consecutive_failures >= max_failures:
        raise typer.Exit(1)


# Control signals coordinate through the cache, so the cache subsystem must be
# booted — otherwise the signal silently no-ops and the operator thinks the
# running scheduler was paused/interrupted when nothing happened.
_CONTROL_REQUIRES: frozenset[CliSubsystem] = frozenset({CliSubsystem.CACHE})

_NO_CACHE_MSG = (
    "arvel: scheduler control signals need a configured cache store; the signal was not delivered."
)


class ScheduleInterruptCommand(Command):
    name: ClassVar[str] = "schedule:interrupt"
    help: ClassVar[str] = "Signal the running scheduler to exit at the next tick boundary."
    requires: ClassVar[frozenset[CliSubsystem]] = _CONTROL_REQUIRES

    def register(self, app: typer.Typer) -> None:
        def _callback() -> None:
            _arvel_async.schedule_async(_send_interrupt())

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError


class SchedulePauseCommand(Command):
    name: ClassVar[str] = "schedule:pause"
    help: ClassVar[str] = "Stop the scheduler from dispatching tasks each tick."
    requires: ClassVar[frozenset[CliSubsystem]] = _CONTROL_REQUIRES

    def register(self, app: typer.Typer) -> None:
        def _callback() -> None:
            _arvel_async.schedule_async(_pause_scheduler())

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError


class ScheduleContinueCommand(Command):
    name: ClassVar[str] = "schedule:continue"
    help: ClassVar[str] = "Resume task dispatching after schedule:pause."
    requires: ClassVar[frozenset[CliSubsystem]] = _CONTROL_REQUIRES

    def register(self, app: typer.Typer) -> None:
        def _callback() -> None:
            _arvel_async.schedule_async(_resume_scheduler())

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError


async def _send_interrupt() -> None:
    from arvel.scheduling.signal import SchedulerSignal

    if not await SchedulerSignal().send_interrupt():
        typer.echo(_NO_CACHE_MSG, err=True)
        raise typer.Exit(2)
    typer.echo("Interrupt signal sent.")


async def _pause_scheduler() -> None:
    from arvel.scheduling.signal import SchedulerSignal

    if not await SchedulerSignal().pause():
        typer.echo(_NO_CACHE_MSG, err=True)
        raise typer.Exit(2)
    typer.echo("Scheduler paused.")


async def _resume_scheduler() -> None:
    from arvel.scheduling.signal import SchedulerSignal

    if not await SchedulerSignal().resume():
        typer.echo(_NO_CACHE_MSG, err=True)
        raise typer.Exit(2)
    typer.echo("Scheduler resumed.")


__all__ = [
    "ScheduleContinueCommand",
    "ScheduleInterruptCommand",
    "ScheduleListCommand",
    "SchedulePauseCommand",
    "ScheduleWorkCommand",
]
