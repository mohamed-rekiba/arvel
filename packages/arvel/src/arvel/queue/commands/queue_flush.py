"""``queue:flush`` — clear all failed jobs."""

from __future__ import annotations

from typing import ClassVar

import typer

from arvel.console import Command, Context
from arvel.console import _async as _arvel_async
from arvel.queue.failed_job_store import FailedJobStore


class QueueFlushCommand(Command):
    name: ClassVar[str] = "queue:flush"
    help: ClassVar[str] = "Delete all failed queue jobs."

    def __init__(self, store: FailedJobStore) -> None:
        self._store = store

    def register(self, app: typer.Typer) -> None:
        cmd_self = self

        def _callback() -> None:
            _arvel_async.schedule_async(cmd_self.flush())

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError

    async def flush(self) -> None:
        await self._store.flush()


__all__ = ["QueueFlushCommand"]
