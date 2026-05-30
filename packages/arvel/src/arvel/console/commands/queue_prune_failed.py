"""queue:prune-failed command (WI-arvel-023)."""

from __future__ import annotations

import asyncio
from typing import Annotated, ClassVar

import typer

from arvel.console import Command, Context
from arvel.console._t import Option as _Option
from arvel.container.errors import BindingResolutionError
from arvel.queue.manager import QueueManager


class QueuePruneFailedCommand(Command):
    name: ClassVar[str] = "queue:prune-failed"
    help: ClassVar[str] = "Delete failed jobs older than --hours"
    needs_application: ClassVar[bool] = True

    def register(self, app: typer.Typer) -> None:
        cmd_self = self

        def _callback(
            *,
            hours: Annotated[
                int,
                _Option("--hours", help="Age threshold in hours"),
            ] = 24,
        ) -> None:
            try:
                count = asyncio.run(cmd_self._run(hours=hours))
            except (BindingResolutionError, RuntimeError) as exc:
                typer.echo(f"arvel: {exc}", err=True)
                raise typer.Exit(code=2) from exc
            typer.echo(f"Pruned {count} failed job(s) older than {hours} hour(s).")

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError

    async def _run(self, *, hours: int) -> int:
        if self.app is None:
            msg = "queue:prune-failed requires a bootstrapped Application"
            raise RuntimeError(msg)
        manager = self.app.container.make(QueueManager)
        prune_method = getattr(manager, "prune_failed", None)
        if prune_method is None:
            msg = "queue:prune-failed: failed-job store does not implement prune_failed()"
            raise RuntimeError(msg)
        result = await prune_method(hours)
        if isinstance(result, int):
            return result
        return 0
