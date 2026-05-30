"""``queue:forget`` — delete one failed job by UUID."""

from __future__ import annotations

from typing import Annotated, ClassVar

import typer

from arvel.console import Command, Context
from arvel.console import _async as _arvel_async
from arvel.console._t import Argument as _Argument
from arvel.queue.failed_job_store import FailedJobStore


class QueueForgetCommand(Command):
    name: ClassVar[str] = "queue:forget"
    help: ClassVar[str] = "Delete a failed job by UUID."

    def __init__(self, store: FailedJobStore) -> None:
        self._store = store

    def register(self, app: typer.Typer) -> None:
        cmd_self = self

        def _callback(
            uuid: Annotated[str, _Argument(help="UUID of the failed job to delete")],
        ) -> None:
            _arvel_async.schedule_async(cmd_self.forget(uuid))

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError

    async def forget(self, uuid: str) -> None:
        deleted = await self._store.delete(uuid)
        if not deleted:
            msg = f"Failed job {uuid!r} not found"
            raise ValueError(msg)


__all__ = ["QueueForgetCommand"]
