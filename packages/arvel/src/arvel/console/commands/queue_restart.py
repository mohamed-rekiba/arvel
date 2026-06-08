"""queue:restart command."""

from __future__ import annotations

from typing import ClassVar

import typer

from arvel.console import Command, Context
from arvel.console import _async as _arvel_async
from arvel.console._subsystem import CliSubsystem
from arvel.queue.restart import QueueRestartSignal


class QueueRestartCommand(Command):
    name: ClassVar[str] = "queue:restart"
    help: ClassVar[str] = "Signal running queue workers to restart gracefully"
    # Writes the restart marker via the cache facade — needs the cache booted.
    requires: ClassVar[frozenset[CliSubsystem]] = frozenset({CliSubsystem.CACHE})

    def register(self, app: typer.Typer) -> None:
        def _callback() -> None:
            async def _dispatch() -> None:
                signal = QueueRestartSignal()
                timestamp = await signal.signal_restart()
                typer.echo(f"Broadcasting queue restart signal at {timestamp.isoformat()}.")

            _arvel_async.schedule_async(_dispatch())

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError
