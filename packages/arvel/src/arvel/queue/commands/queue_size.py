"""``queue:size`` — print the number of pending jobs on a queue."""

from __future__ import annotations

from typing import Annotated, ClassVar

import typer

from arvel.console import Command, Context
from arvel.console import _async as _arvel_async
from arvel.console._subsystem import CliSubsystem
from arvel.console._t import Option as _Option
from arvel.queue.manager import QueueManager


class QueueSizeCommand(Command):
    name: ClassVar[str] = "queue:size"
    help: ClassVar[str] = "Show the number of pending jobs on a queue."
    # Provider-attached (DI __init__), so not an entry point; keep in sync with
    # PROVIDER_COMMAND_REQUIRES (drift-guarded).
    requires: ClassVar[frozenset[CliSubsystem]] = frozenset(
        {CliSubsystem.QUEUE, CliSubsystem.USER_PROVIDERS}
    )

    def __init__(self, manager: QueueManager) -> None:
        self._manager = manager

    def register(self, app: typer.Typer) -> None:
        cmd_self = self

        def _callback(
            queue: Annotated[
                str, _Option("--queue", help="Name of the queue to inspect")
            ] = "default",
        ) -> None:
            _arvel_async.schedule_async(cmd_self.show_size(queue))

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError

    async def show_size(self, queue: str) -> None:
        conn = self._manager.connection()
        size = await conn.size(queue)
        typer.echo(f"Queue '{queue}': {size} pending job(s).")


__all__ = ["QueueSizeCommand"]
