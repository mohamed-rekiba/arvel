"""Phase 8 — Job + QueueManager (taskiq) dispatch + serialization."""

from __future__ import annotations

from arvel.queue import Job, QueueManager, deserialize, serialize

RAN: list[str] = []


class RecordJob(Job):
    queue = "media"

    def __init__(self, value: str) -> None:
        self.value = value

    async def handle(self) -> None:
        RAN.append(self.value)


async def test_serialize_roundtrip() -> None:
    payload = serialize(RecordJob, ("hello",), {})
    job = await deserialize(payload)
    assert isinstance(job, RecordJob)
    assert job.value == "hello"


async def test_push_runs_job_on_broker() -> None:
    RAN.clear()
    manager = QueueManager()
    try:
        task = await manager.push(RecordJob, ("pushed",), {})
        await task.wait_result()
        assert RAN == ["pushed"]
    finally:
        if manager._started:
            await manager.broker.shutdown()


async def test_dispatch_serializes_and_runs() -> None:
    RAN.clear()
    task = await RecordJob.dispatch("dispatched")
    await task.wait_result()
    assert RAN == ["dispatched"]


async def test_push_instance_runs_job_on_broker() -> None:
    # Regression: push_instance serializes as {job, state}; the broker runner must deserialize THAT
    # shape, not the args/kwargs shape — else every instance-pushed job (queued mailables/
    # notifications, chains/batches, FailedJob.retry) KeyErrors when the worker executes it.
    RAN.clear()
    manager = QueueManager()
    try:
        task = await manager.push_instance(RecordJob("instance"))
        await task.wait_result()
        assert RAN == ["instance"]  # handle() actually ran (no KeyError in the runner)
    finally:
        if manager._started:
            await manager.broker.shutdown()
