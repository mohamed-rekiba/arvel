"""``queue:failed`` — list all failed jobs."""

from __future__ import annotations

from typing import Annotated, ClassVar

import typer

from arvel.console import Command, Context
from arvel.console import _async as _arvel_async
from arvel.console._t import Option as _Option
from arvel.queue.failed_job_store import FailedJobStore


class QueueFailedCommand(Command):
    name: ClassVar[str] = "queue:failed"
    help: ClassVar[str] = "List all failed queue jobs."

    def __init__(self, store: FailedJobStore) -> None:
        self._store = store

    def register(self, app: typer.Typer) -> None:
        cmd_self = self

        def _callback(
            queue: Annotated[str, _Option("--queue", help="Filter by queue name")] = "",
        ) -> None:
            _arvel_async.schedule_async(cmd_self.list_failed(queue or None))

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError

    async def list_failed(self, queue: str | None) -> None:
        rows = await self._store.list_all()
        if queue is not None:
            rows = [r for r in rows if r.queue == queue]
        if not rows:
            return
        for row in rows:
            typer.echo(f"{row.uuid}  {row.queue}  {row.failed_at}")


__all__ = ["QueueFailedCommand"]
