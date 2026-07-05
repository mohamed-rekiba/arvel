"""Integration (doc 20) — jobs round-trip through a real AMQP broker (RabbitMQ/LavinMQ), and
QUEUE-RELIABILITY's chain/retry-release/visibility-timeout mechanics against a real Postgres
`jobs` table + a real broker (not the in-memory/SQLite unit-test doubles).

The in-memory / Redis broker paths don't exercise the AMQP consumer setup; only a real broker does.
This dispatches a job, runs the in-process worker against RabbitMQ, and asserts the handler ran on the
other side of the broker — proving JSON arg serialization + consume + execute end to end.

Regression guard: `QueueManager.work()` must mark the broker as a worker before startup, or
taskiq-aio-pika raises "Call startup before starting listening" (the consumer queue is never declared).
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from pathlib import Path
from typing import ClassVar

import pytest
import sqlalchemy as sa

from arvel.database import ConnectionResolver
from arvel.kernel import Application, set_application
from arvel.queue import Bus, Job, QueuedJob, QueueManager

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


class ChainStep(Job):
    """Appends its label to a shared file — observable proof of execution order."""

    def __init__(self, path: str, label: str) -> None:
        self.path = path
        self.label = label

    async def handle(self) -> None:
        target = Path(self.path)
        existing = target.read_text() if target.exists() else ""
        target.write_text(existing + self.label)


async def test_chain_runs_in_order_across_worker_passes_over_amqp(
    rabbitmq_url: str, tmp_path: Path
) -> None:
    """A1 over a real broker: each chain link only dispatches once the prior one's job — travelling
    through an actual AMQP round-trip — has completed, so the file ends up "abc", never scrambled."""
    target = tmp_path / "chain_order.txt"
    app = Application()
    app.make("config").set("queue", {"default": "amqp", "url": rabbitmq_url})
    manager = QueueManager(app=app)
    app.instance("queue", manager)
    set_application(app)
    try:
        await Bus.chain(
            [
                ChainStep(str(target), "a"),
                ChainStep(str(target), "b"),
                ChainStep(str(target), "c"),
            ]
        ).dispatch(manager=manager)

        worker = asyncio.create_task(manager.work(release_interval=0.2))
        got = None
        for _ in range(200):  # each link is its own broker round-trip — allow generous time
            if target.exists() and target.read_text() == "abc":
                got = target.read_text()
                break
            await asyncio.sleep(0.1)
        worker.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker

        assert got == "abc", f"chain did not run strictly in order over AMQP (got {got!r})"
    finally:
        with contextlib.suppress(Exception):
            await manager.broker.shutdown()
        set_application(None)


class FlakyOnceJob(Job):
    """Fails its first attempt, then succeeds — with a real backoff, so a working release (not an
    inline sleep) is what lets an unrelated second job drain in the meantime."""

    tries = 2
    backoff = 4

    def __init__(self, path: str) -> None:
        self.path = path
        self.calls = 0

    async def handle(self) -> None:
        self.calls += 1
        if self.calls == 1:
            raise ValueError("first attempt fails")
        Path(self.path).write_text("recovered")


class WriteImmediately(Job):
    def __init__(self, path: str) -> None:
        self.path = path

    async def handle(self) -> None:
        Path(self.path).write_text("second-ran")


async def test_retry_release_drains_a_second_job_while_the_first_waits_its_backoff(
    rabbitmq_url: str, postgres_url: str, tmp_path: Path
) -> None:
    """B1 over real infra: the first job's failed attempt is released (Postgres `jobs` row, future
    `available_at`) rather than blocking the worker — an unrelated second job finishes first."""
    first_target = tmp_path / "first.txt"
    second_target = tmp_path / "second.txt"

    app = Application()
    app.make("config").set("queue", {"default": "amqp", "url": rabbitmq_url})
    db = ConnectionResolver({"default": {"url": postgres_url}})
    app.instance("db", db)
    manager = QueueManager(app=app)
    app.instance("queue", manager)
    set_application(app)
    QueuedJob.set_connection(db)
    await db.execute(sa.schema.CreateTable(QueuedJob.__table__))
    try:
        await manager.push_instance(FlakyOnceJob(str(first_target)))
        await manager.push_instance(WriteImmediately(str(second_target)))

        worker = asyncio.create_task(manager.work(release_interval=0.3))
        # the unrelated second job finishes quickly — not queued behind the first job's 4s backoff
        second_done = False
        for _ in range(30):
            if second_target.exists():
                second_done = True
                break
            await asyncio.sleep(0.1)
        assert second_done, "the second job was blocked behind the first job's retry backoff"

        # the first job eventually recovers once release_due_jobs redispatches it past backoff
        first_done = None
        for _ in range(150):
            if first_target.exists():
                first_done = first_target.read_text()
                break
            await asyncio.sleep(0.1)
        worker.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker

        assert first_done == "recovered"
    finally:
        with contextlib.suppress(Exception):
            await manager.broker.shutdown()
        with contextlib.suppress(Exception):
            await db.execute(sa.schema.DropTable(QueuedJob.__table__))
        await db.dispose()
        set_application(None)


class ReclaimJob(Job):
    def __init__(self, path: str) -> None:
        self.path = path

    async def handle(self) -> None:
        Path(self.path).write_text("reclaimed")


async def test_visibility_timeout_reclaims_a_stuck_reservation_over_amqp(
    rabbitmq_url: str, postgres_url: str, tmp_path: Path
) -> None:
    """A row whose worker "died" (reserved_at forced old, past `retry_after`) is reclaimed and
    re-run by a fresh worker pass, against a real Postgres `jobs` table."""
    target = tmp_path / "reclaimed.txt"

    app = Application()
    app.make("config").set("queue", {"default": "amqp", "url": rabbitmq_url, "retry_after": 1})
    db = ConnectionResolver({"default": {"url": postgres_url}})
    app.instance("db", db)
    manager = QueueManager(app=app)
    app.instance("queue", manager)
    set_application(app)
    QueuedJob.set_connection(db)
    await db.execute(sa.schema.CreateTable(QueuedJob.__table__))
    try:
        await manager.dispatch_after(0, ReclaimJob(str(target)))
        row = (await QueuedJob.all())[0]
        # simulate a worker that claimed the row then died before push_instance/delete
        await QueuedJob.where("id", "=", row.id).update({"reserved_at": int(time.time()) - 5})

        worker = asyncio.create_task(manager.work(release_interval=0.2))
        got = None
        for _ in range(100):
            if target.exists():
                got = target.read_text()
                break
            await asyncio.sleep(0.1)
        worker.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker

        assert got == "reclaimed"
    finally:
        with contextlib.suppress(Exception):
            await manager.broker.shutdown()
        with contextlib.suppress(Exception):
            await db.execute(sa.schema.DropTable(QueuedJob.__table__))
        await db.dispose()
        set_application(None)
