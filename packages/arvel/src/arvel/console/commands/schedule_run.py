"""schedule:run — alias for ``schedule:work --once`` (Laravel artisan parity)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar

import typer

from arvel.console import Command, Context
from arvel.console import _async as _arvel_async
from arvel.console._subsystem import CliSubsystem
from arvel.console.commands.schedule_commands import resolve_kernel


class ScheduleRunCommand(Command):
    name: ClassVar[str] = "schedule:run"
    help: ClassVar[str] = "Alias for `schedule:work --once` — run the scheduler once and exit."
    requires: ClassVar[frozenset[CliSubsystem]] = frozenset(
        {CliSubsystem.SCHEDULER, CliSubsystem.USER_PROVIDERS}
    )

    def register(self, app: typer.Typer) -> None:
        cmd_self = self

        def _callback() -> None:
            try:
                kernel = resolve_kernel(cmd_self)
            except Exception as exc:
                typer.echo(
                    f"arvel: schedule:run failed to resolve scheduler: {exc}",
                    err=True,
                )
                raise typer.Exit(code=2) from exc
            _arvel_async.schedule_async(kernel.run_due_tasks(datetime.now(UTC)))

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError
