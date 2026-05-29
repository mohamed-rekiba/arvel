"""queue:restart command (WI-arvel-023)."""

from __future__ import annotations

import asyncio
from typing import ClassVar

import typer

from arvel.console import Command, Context
from arvel.queue.restart import QueueRestartSignal


class QueueRestartCommand(Command):
    name: ClassVar[str] = "queue:restart"
    help: ClassVar[str] = "Signal running queue workers to restart gracefully"

    def register(self, app: typer.Typer) -> None:
        def _callback() -> None:
            signal = QueueRestartSignal()
            timestamp = asyncio.run(signal.signal_restart())
            typer.echo(f"Broadcasting queue restart signal at {timestamp.isoformat()}.")

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError
