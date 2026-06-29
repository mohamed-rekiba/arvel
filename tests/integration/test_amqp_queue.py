"""Integration (doc 20) — jobs round-trip through a real AMQP broker (RabbitMQ/LavinMQ).

The in-memory / Redis broker paths don't exercise the AMQP consumer setup; only a real broker does.
This dispatches a job, runs the in-process worker against RabbitMQ, and asserts the handler ran on the
other side of the broker — proving JSON arg serialization + consume + execute end to end.

Regression guard: `QueueManager.work()` must mark the broker as a worker before startup, or
taskiq-aio-pika raises "Call startup before starting listening" (the consumer queue is never declared).
"""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from typing import ClassVar

import pytest

from arvel.kernel import Application, set_application
from arvel.queue import Job, QueueManager

pytestmark = pytest.mark.integration


class WriteTokenJob(Job):
    """Writes a token to a path — an observable side effect that proves the handler executed after
    the job (with its args) travelled through the broker as JSON."""

    queue: ClassVar[str] = "default"

    def __init__(self, path: str, token: str) -> None:
        self.path = path
        self.token = token

    async def handle(self) -> None:
        Path(self.path).write_text(self.token)


async def test_job_round_trips_through_real_amqp_broker(rabbitmq_url: str, tmp_path: Path) -> None:
    target = tmp_path / "amqp_token.txt"
    app = Application()
    app.make("config").set("queue", {"default": "amqp", "url": rabbitmq_url})
    manager = QueueManager(app=app)
    app.instance("queue", manager)
    set_application(app)
    try:
        await WriteTokenJob.dispatch(str(target), "AMQP-OK")

        worker = asyncio.create_task(manager.work(release_interval=0.2))
        got = None
        for _ in range(150):  # up to ~15s for the broker round-trip + consume
            if target.exists():
                got = target.read_text()
                break
            await asyncio.sleep(0.1)
        worker.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker

        assert got == "AMQP-OK", "job did not execute after travelling through the AMQP broker"
    finally:
        with contextlib.suppress(Exception):
            await manager.broker.shutdown()
        set_application(None)
