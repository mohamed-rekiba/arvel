"""Queues (doc 12) — visibility timeout: a `jobs` row reserved by a worker that died before
finishing (claimed via `reserved_at`, never deleted) is reclaimed once `retry_after` has passed and
picked up by another pass, instead of leaking forever."""

from __future__ import annotations

import time

import sqlalchemy as sa
from taskiq import InMemoryBroker

from arvel.database import ConnectionResolver
from arvel.kernel import Application, set_application
from arvel.queue import Job, QueuedJob, QueueManager

RAN: list[str] = []


class Greet(Job):
    def __init__(self, who: str) -> None:
        self.who = who

    async def handle(self) -> None:
        RAN.append(self.who)


class QuickTimeout(Job):
    """A per-job `retry_after` override (5s, well under the 90s queue-config default)."""

    retry_after = 5

    async def handle(self) -> None:
        RAN.append("quick")


#: captured log-context snapshot from ContextProbe.handle (module-level so the job is serializable)
_CAPTURED: dict[str, object] = {}


class ContextProbe(Job):
    """Records the ambient log context observed while its handle() runs (correlation-id tests)."""

    async def handle(self) -> None:
        import structlog

        _CAPTURED.update(structlog.contextvars.get_contextvars())


async def _setup() -> tuple[QueueManager, ConnectionResolver]:
    RAN.clear()
    app = Application()
    db = ConnectionResolver()
    app.instance("db", db)
    manager = QueueManager(app, broker=InMemoryBroker(await_inplace=True))
    app.instance("queue", manager)
    set_application(app)
    QueuedJob.set_connection(db)
    await db.execute(sa.schema.CreateTable(QueuedJob.__table__))
    return manager, db


async def test_stuck_reservation_is_reclaimed_after_retry_after_and_rerun() -> None:
    manager, db = await _setup()
    try:
        now = int(time.time())
        await manager.dispatch_after(0, Greet("zombie"))
        row = (await QueuedJob.all())[0]
        # simulate a worker that claimed the row then died before push_instance/delete
        await QueuedJob.where("id", "=", row.id).update({"reserved_at": now - 200})

        released = await manager.release_due_jobs(now=now)
        assert released == 1
        assert RAN == ["zombie"]
        assert await QueuedJob.all() == []
    finally:
        set_application(None)
        await db.dispose()


async def test_a_freshly_reserved_row_is_left_alone() -> None:
    """A row reserved moments ago (still within `retry_after`) is presumed still in flight."""
    manager, db = await _setup()
    try:
        now = int(time.time())
        await manager.dispatch_after(0, Greet("still-running"))
        row = (await QueuedJob.all())[0]
        await QueuedJob.where("id", "=", row.id).update({"reserved_at": now})

        released = await manager.release_due_jobs(now=now)
        assert released == 0
        assert RAN == []
        assert len(await QueuedJob.all()) == 1
    finally:
        set_application(None)
        await db.dispose()


async def test_per_job_retry_after_overrides_the_queue_config_default() -> None:
    manager, db = await _setup()
    try:
        now = int(time.time())
        await manager.dispatch_after(0, QuickTimeout())
        row = (await QueuedJob.all())[0]
        # Simulate a crashed claim: reserved 10s ago with QuickTimeout's 5s override baked into
        # reserved_until at claim time (reserved_at + 5 = now - 5, already past) — so it's overdue
        # under its own override even though the 90s config default hasn't elapsed.
        await QueuedJob.where("id", "=", row.id).update(
            {"reserved_at": now - 10, "reserved_until": now - 5}
        )

        released = await manager.release_due_jobs(now=now)
        assert released == 1
        assert RAN == ["quick"]
    finally:
        set_application(None)
        await db.dispose()


async def test_poison_payload_is_parked_and_does_not_block_the_due_loop() -> None:
    """An undeserializable ("poison") row must be claimed+parked, not left available to re-block the
    loop every tick — and a good job dispatched alongside it must still run (F-027 regression guard)."""
    manager, db = await _setup()
    try:
        now = int(time.time())
        # a poison row (garbage payload), due now, unreserved
        await QueuedJob.create(
            queue="default",
            payload="!!not-a-serialized-job!!",
            attempts=0,
            reserved_at=None,
            reserved_until=None,
            available_at=now,
            created_at=now,
        )
        await manager.dispatch_after(0, Greet(who="ok"))  # a good job, also due now

        released = await manager.release_due_jobs(now=now)
        assert released == 1  # only the good job was pushed
        assert RAN == ["ok"]  # good job ran; the poison did not crash the loop
        # the poison row is parked (claimed) with a visibility deadline, not deleted, not re-run
        rows = await QueuedJob.where_not_null("reserved_at").get()
        assert len(rows) == 1
        assert rows[0].reserved_until is not None
    finally:
        set_application(None)
        await db.dispose()


async def test_job_execution_binds_a_uuid7_job_id_into_the_log_context() -> None:
    """Every queue job runs with a uuid7 `job_id` (+ job name) bound into the log context — the
    queue-side counterpart of HTTP's request_id — so all of a job's log lines correlate."""
    import uuid

    import structlog

    captured: dict[str, object] = {}

    class Probe(Job):
        async def handle(self) -> None:
            captured.update(structlog.contextvars.get_contextvars())

    manager, db = await _setup()
    try:
        await manager._worker._invoke(Probe())
        assert captured.get("job") == "Probe"
        job_id = captured.get("job_id")
        assert isinstance(job_id, str)
        assert uuid.UUID(job_id).version == 7  # a real uuid7, not an arbitrary string
        assert "request_id" not in captured  # no originating request → no propagated id
        # the correlation is scoped to the job — cleared after execution
        assert "job_id" not in structlog.contextvars.get_contextvars()
    finally:
        set_application(None)
        await db.dispose()


async def test_full_request_log_context_propagates_into_the_job() -> None:
    """A job dispatched while the request has bound log context carries ALL of it across the broker:
    on the worker its log context has request_id + every other bound value (user_id, tenant_id, …),
    PLUS its own fresh job_id — so the request and the queue jobs it spawned share full context."""
    import structlog

    from arvel.kernel.logging import LogManager
    from arvel.queue.serialization import deserialize_instance, serialize_instance

    _CAPTURED.clear()
    manager, db = await _setup()
    try:
        # simulate an in-flight API request with a rich bound log context
        with LogManager.bound_context(request_id="req-abc-123", user_id=42, tenant_id="acme"):
            payload = serialize_instance(ContextProbe())  # captures the whole context
        # ...worker (no ambient context) picks it up and runs it
        job = await deserialize_instance(payload)
        await manager._worker._invoke(job)
        assert _CAPTURED.get("request_id") == "req-abc-123"
        assert _CAPTURED.get("user_id") == 42  # arbitrary bound values propagate too
        assert _CAPTURED.get("tenant_id") == "acme"
        assert isinstance(_CAPTURED.get("job_id"), str)  # plus its own execution id
        assert _CAPTURED["job_id"] != "req-abc-123"
    finally:
        structlog.contextvars.clear_contextvars()
        set_application(None)
        await db.dispose()
