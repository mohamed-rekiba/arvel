"""``queue:work`` — start the worker loop.

Honors the :class:`arvel.console.Command` contract by overriding ``register()``
to declare its Typer-level flags (``--queue``, ``--stop-when-empty``). The
``handle(ctx)`` method is intentionally ``raise NotImplementedError`` because
the queue worker runs as an async loop driven by the Typer callback —
``Command.handle(ctx)`` is the synchronous slot used by the in-process
``Application.run()`` path, which doesn't apply to a long-running worker.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
from typing import Annotated, ClassVar

import typer

from arvel.console import Command, Context
from arvel.console import _async as _arvel_async
from arvel.console._subsystem import CliSubsystem
from arvel.console._t import Option as _Option
from arvel.queue.manager import QueueManager
from arvel.queue.restart import QueueRestartSignal
from arvel.queue.worker import Worker


class QueueWorkCommand(Command):
    name: ClassVar[str] = "queue:work"
    help: ClassVar[str] = "Start the queue worker."
    # CACHE backs the restart signal; without it queue:restart can't reach this
    # worker. Keep in sync with PROVIDER_COMMAND_REQUIRES (drift-guarded).
    requires: ClassVar[frozenset[CliSubsystem]] = frozenset(
        {CliSubsystem.QUEUE, CliSubsystem.CACHE, CliSubsystem.USER_PROVIDERS}
    )

    def __init__(
        self,
        manager: QueueManager,
        *,
        failed_job_store: object | None = None,
        restart_signal: QueueRestartSignal | None = None,
    ) -> None:
        self._manager = manager
        self._failed_job_store = failed_job_store
        # Default to the framework's cache-backed signal so `queue:restart`
        # actually reaches workers without callers wiring it explicitly.
        self._restart_signal = restart_signal or QueueRestartSignal()

    def register(self, app: typer.Typer) -> None:
        cmd_self = self

        def _callback(
            queue: Annotated[
                str, _Option("--queue", help="Name of the queue to consume")
            ] = "default",
            *,
            stop_when_empty: Annotated[
                bool,
                _Option(
                    "--stop-when-empty",
                    help="Exit when the queue is drained (one-shot mode)",
                ),
            ] = False,
        ) -> None:
            _arvel_async.schedule_async(
                cmd_self.run_worker(queue=queue, stop_when_empty=stop_when_empty)
            )

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError

    async def run_worker(self, *, queue: str, stop_when_empty: bool) -> None:
        stop = asyncio.Event()

        def _sigterm_handler() -> None:
            stop.set()

        loop = asyncio.get_event_loop()
        with contextlib.suppress(NotImplementedError, RuntimeError):
            loop.add_signal_handler(signal.SIGTERM, _sigterm_handler)

        worker = Worker(
            self._manager,
            queue=queue,
            failed_job_store=self._failed_job_store,
            restart_signal=self._restart_signal,
        )
        if stop_when_empty:
            await worker.drain_then_stop()
            return
        await worker.run_until(stop)


__all__ = ["QueueWorkCommand"]
