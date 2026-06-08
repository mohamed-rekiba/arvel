"""queue:clear command."""

from __future__ import annotations

from typing import Annotated, ClassVar

import typer

from arvel.console import Command, Context
from arvel.console import _async as _arvel_async
from arvel.console._subsystem import CliSubsystem
from arvel.console._t import Option as _Option
from arvel.container.errors import BindingResolutionError
from arvel.queue.manager import QueueManager


class QueueClearCommand(Command):
    name: ClassVar[str] = "queue:clear"
    help: ClassVar[str] = "Remove all pending jobs from a queue"
    # QUEUE closure pulls in DATABASE; USER_PROVIDERS for user-defined queue connections.
    requires: ClassVar[frozenset[CliSubsystem]] = frozenset(
        {CliSubsystem.QUEUE, CliSubsystem.USER_PROVIDERS}
    )

    def register(self, app: typer.Typer) -> None:
        cmd_self = self

        def _callback(
            *,
            queue: Annotated[str, _Option("--queue", help="Queue name to clear")] = "default",
            connection: Annotated[  # noqa: ARG001 — reserved for multi-connection support
                str, _Option("--connection", help="Queue connection")
            ] = "default",
        ) -> None:
            async def _dispatch() -> None:
                try:
                    count = await cmd_self._run(queue=queue)
                except (BindingResolutionError, RuntimeError) as exc:
                    typer.echo(f"arvel: {exc}", err=True)
                    raise typer.Exit(code=2) from exc
                typer.echo(f"Cleared {count} job(s) from queue '{queue}'.")

            _arvel_async.schedule_async(_dispatch())

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError

    async def _run(self, *, queue: str) -> int:
        if self.app is None:
            msg = "queue:clear requires a bootstrapped Application"
            raise RuntimeError(msg)
        manager = self.app.container.make(QueueManager)
        clear_method = getattr(manager, "clear", None)
        if clear_method is None:
            msg = "queue:clear: connection driver does not implement clear()"
            raise RuntimeError(msg)
        result = await clear_method(queue)
        if isinstance(result, int):
            return result
        return 0
