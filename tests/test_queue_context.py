"""Queues (doc 12) — Context carry-over (SUPPORT-FOUNDATION seam, story 02): `Context.dehydrate()`
rides along in the job payload at dispatch time; the worker `Context.hydrate()`s it before
`handle()` runs — so a dispatch-time value is what the job sees, regardless of whatever happens to
be ambient in the task that actually executes it."""

from __future__ import annotations

from taskiq import InMemoryBroker

from arvel.kernel import Application, set_application
from arvel.queue import (
    Job,
    QueueManager,
    deserialize_instance,
    run_job_with_retries,
    serialize_instance,
)
from arvel.support.context import Context

SEEN: list[str] = []


class ReadsContext(Job):
    async def handle(self) -> None:
        SEEN.append(Context.get("tenant", "MISSING"))


async def test_context_hydrated_from_the_job_payload_overrides_whatever_is_ambient() -> None:
    """The precise guarantee: the dispatch-time value wins, even if the executing task's ambient
    Context later says something else (a different job/request reusing the same process)."""
    SEEN.clear()
    Context.add("tenant", "acme")
    payload = serialize_instance(ReadsContext())
    Context.forget("tenant")
    Context.add("tenant", "someone-elses-tenant")  # ambient at "run time" — must NOT leak in
    try:
        restored = await deserialize_instance(payload)
        await run_job_with_retries(restored)
        assert SEEN == ["acme"]
    finally:
        Context.forget("tenant")


async def test_dispatch_time_context_value_is_visible_inside_the_job_end_to_end() -> None:
    """The same guarantee through the public dispatch path (`push_instance` -> a worker running
    the job) rather than the primitives directly."""
    SEEN.clear()
    app = Application()
    manager = QueueManager(app, broker=InMemoryBroker(await_inplace=True))
    app.instance("queue", manager)
    set_application(app)
    try:
        Context.add("tenant", "acme")
        await manager.push_instance(ReadsContext())
        assert SEEN == ["acme"]
    finally:
        Context.forget("tenant")
        set_application(None)


async def test_no_context_set_at_dispatch_reads_as_missing_in_the_job() -> None:
    SEEN.clear()
    app = Application()
    manager = QueueManager(app, broker=InMemoryBroker(await_inplace=True))
    app.instance("queue", manager)
    set_application(app)
    try:
        assert not Context.has("tenant")
        await manager.push_instance(ReadsContext())
        assert SEEN == ["MISSING"]
    finally:
        set_application(None)
