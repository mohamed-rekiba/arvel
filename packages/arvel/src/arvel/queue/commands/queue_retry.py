"""``queue:retry`` — re-dispatch a failed job by UUID."""

from __future__ import annotations

from typing import Annotated, ClassVar

import typer

from arvel.console import Command, Context
from arvel.console import _async as _arvel_async
from arvel.console._t import Argument as _Argument
from arvel.console._t import Option as _Option
from arvel.queue.bus import Bus
from arvel.queue.envelope import JobEnvelope
from arvel.queue.failed_job_store import FailedJobStore
from arvel.queue.manager import QueueManager
from arvel.queue.registry import deserialize_job


class QueueRetryCommand(Command):
    name: ClassVar[str] = "queue:retry"
    help: ClassVar[str] = "Re-dispatch a failed job by UUID."

    def __init__(self, manager: QueueManager, store: FailedJobStore) -> None:
        self._store = store
        self._bus = Bus(manager)

    def register(self, app: typer.Typer) -> None:
        cmd_self = self

        def _callback(
            uuid: Annotated[
                str | None,
                _Argument(help="UUID of the failed job to retry"),
            ] = None,
            *,
            all_failed: Annotated[
                bool,
                _Option("--all", help="Retry every failed job"),
            ] = False,
        ) -> None:
            if all_failed and uuid is not None:
                raise typer.BadParameter("--all cannot be combined with a UUID")
            if all_failed:
                _arvel_async.schedule_async(cmd_self.retry_all())
                return
            if uuid is None:
                raise typer.BadParameter("uuid is required unless --all is passed")
            _arvel_async.schedule_async(cmd_self.retry(uuid))

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError

    async def retry(self, uuid: str) -> None:
        row = await self._store.find(uuid)
        if row is None:
            msg = f"Failed job {uuid!r} not found"
            raise ValueError(msg)
        envelope = JobEnvelope.from_json(row.payload)
        envelope.attempts = 0
        job = deserialize_job(envelope)
        await self._bus.dispatch(job)
        await self._store.delete(uuid)

    async def retry_all(self) -> int:
        rows = await self._store.list_all()
        for row in rows:
            await self.retry(row.uuid)
        return len(rows)


__all__ = ["QueueRetryCommand"]
