"""Notifications (doc 16/12) — E15: a notification declares queued-rail middleware via
`middleware()`; `SendQueuedNotification` (the per-channel queued job) surfaces it into the
EXISTING job-middleware onion (`Job.middleware()` -> `Pipeline`, E14) — no parallel throttle.
Queued-rail only: an inline send has no job, so no middleware ever runs.

Notification classes live at module level (not nested in test functions): `SendQueuedNotification`
stores a notification ENCODED (`__class__` as a qualified name) and `middleware()` reloads it via
that name — a `<locals>`-qualified class can't be re-imported, same constraint a real broker hop
would hit."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from taskiq import InMemoryBroker

from arvel.cache.provider import CacheServiceProvider
from arvel.database import ConnectionResolver
from arvel.events import ShouldQueue
from arvel.http.rate_limiter import RateLimiter
from arvel.kernel import Application, app, set_application
from arvel.notifications import Notification, NotificationManager, SendQueuedNotification
from arvel.queue import QueuedJob, QueueManager
from arvel.queue.middleware import JobShouldBeReleased, RateLimited
from arvel.queue.worker import _wrap_with_middleware  # pyright: ignore[reportPrivateUsage]

DELIVERED: list[str] = []


class FakeQueue:
    """Captures pushed jobs instead of running them — lets a test inspect what `send()` enqueued
    before deciding how to drain it."""

    def __init__(self) -> None:
        self.pushed: list[Any] = []

    async def push_instance(self, job: Any) -> None:
        self.pushed.append(job)


class Throttled(Notification, ShouldQueue):
    """A queued single-channel notification declaring a `RateLimited` middleware. The limiter is
    resolved fresh from the bound cache on each call — never stored on `self` — matching the
    sync-reconstruction contract: an attribute has to survive `encode_instance`/msgspec across the
    queue, and a live limiter can't."""

    def via(self, notifiable: Any) -> list[str]:
        return ["database"]

    def to_array(self, notifiable: Any) -> dict[str, Any]:
        return {"msg": "hi"}

    def middleware(self) -> list[Any]:
        return [RateLimited(RateLimiter(app().make("cache")), "throttle-key", max_attempts=2)]


class TwoChannelThrottled(Throttled):
    """Same declared middleware, two channels — proves each channel's job carries it independently."""

    def via(self, notifiable: Any) -> list[str]:
        return ["database", "mail"]

    def middleware(self) -> list[Any]:
        return [RateLimited(RateLimiter(app().make("cache")), "two-channel-key", max_attempts=2)]


class Plain(Notification, ShouldQueue):
    """Queued, single-channel, no `middleware()` override — the default `[]` applies."""

    def via(self, notifiable: Any) -> list[str]:
        return ["database"]

    def to_array(self, notifiable: Any) -> dict[str, Any]:
        return {"msg": "hi"}


class InlineThrottled(Notification):
    """NOT `ShouldQueue` — an inline send has no job, so this declared middleware never runs."""

    def via(self, notifiable: Any) -> list[str]:
        return ["database"]

    def to_array(self, notifiable: Any) -> dict[str, Any]:
        return {"msg": "hi"}

    def middleware(self) -> list[Any]:
        return [RateLimited(RateLimiter(app().make("cache")), "inline-key", max_attempts=1)]


class InvoicePaidQueued(Notification, ShouldQueue):
    """`docs/notifications.md`'s worked example notification."""

    def via(self, notifiable: Any) -> list[str]:
        return ["database"]

    def to_array(self, notifiable: Any) -> dict[str, Any]:
        return {"paid": True}


class ReminderLater(Notification):
    """`docs/notifications.md`'s `later(delay, ...)` example notification — records delivery in
    `DELIVERED` (a side effect, not the return value, since nothing else observes a released job)."""

    def via(self, notifiable: Any) -> list[str]:
        return ["database"]

    def to_array(self, notifiable: Any) -> dict[str, Any]:
        DELIVERED.append("reminder")
        return {"reminder": True}


async def test_notification_middleware_defaults_to_empty() -> None:
    assert Notification().middleware() == []


async def test_should_queue_enqueues_one_job_per_channel_each_carrying_declared_middleware() -> (
    None
):
    application = Application()
    CacheServiceProvider(application).register()
    mgr = NotificationManager(application)
    application.instance("notifications", mgr)
    fake = FakeQueue()
    application.instance("queue", fake)
    set_application(application)
    try:
        result = await mgr.send(object(), TwoChannelThrottled())
        assert result == {"queued": True}
        assert len(fake.pushed) == 2
        for job in fake.pushed:
            declared = job.middleware()
            assert len(declared) == 1
            assert isinstance(declared[0], RateLimited)
    finally:
        set_application(None)


async def test_rate_limited_notification_throttles_over_the_limit_on_queued_rail() -> None:
    """5 sends, max_attempts=2: exactly 2 deliver, 3 are released (deferred) — never failed."""
    application = Application()
    CacheServiceProvider(application).register()
    mgr = NotificationManager(application)
    application.instance("notifications", mgr)
    fake = FakeQueue()
    application.instance("queue", fake)
    set_application(application)
    try:
        for _ in range(5):
            await mgr.send(object(), Throttled())
        assert len(fake.pushed) == 5

        delivered = 0
        released = 0
        for job in fake.pushed:
            run = _wrap_with_middleware(job, job.handle)
            try:
                await run()
                delivered += 1
            except JobShouldBeReleased:
                released += 1
        assert delivered == 2
        assert released == 3
    finally:
        set_application(None)


async def test_notification_without_middleware_delivers_all() -> None:
    """The same drain, minus the `middleware()` override: nothing throttles, all 5 deliver."""
    application = Application()
    mgr = NotificationManager(application)
    application.instance("notifications", mgr)
    fake = FakeQueue()
    application.instance("queue", fake)
    set_application(application)
    try:
        for _ in range(5):
            await mgr.send(object(), Plain())
        assert len(fake.pushed) == 5

        delivered = 0
        for job in fake.pushed:
            run = _wrap_with_middleware(job, job.handle)
            await run()
            delivered += 1
        assert delivered == 5
    finally:
        set_application(None)


async def test_inline_send_ignores_declared_middleware() -> None:
    """Queued-rail-only: an inline (non-ShouldQueue) send has no job, so the declared middleware
    is never consulted — every send goes through, even past `max_attempts`."""
    application = Application()
    CacheServiceProvider(application).register()
    mgr = NotificationManager(application)
    application.instance("notifications", mgr)
    set_application(application)
    try:
        for _ in range(5):
            result = await mgr.send(object(), InlineThrottled())
            assert result == {"database": {"msg": "hi"}}  # no queue bound -> inline, every time
    finally:
        set_application(None)


async def test_docs_should_queue_example() -> None:
    """`docs/notifications.md`'s worked example: a `ShouldQueue` notify returns `{"queued": True}`
    and, once its job runs (drained), is delivered."""
    application = Application()
    mgr = NotificationManager(application)
    application.instance("notifications", mgr)
    fake = FakeQueue()
    application.instance("queue", fake)
    set_application(application)
    try:
        result = await mgr.send(object(), InvoicePaidQueued())
        assert result == {"queued": True}
        assert isinstance(fake.pushed[0], SendQueuedNotification)
        delivered = await fake.pushed[0].handle()
        assert delivered == {"database": {"paid": True}}
    finally:
        set_application(None)


async def test_docs_later_delay_example() -> None:
    """`docs/notifications.md`'s `later(delay, ...)` example: schedules via `dispatch_after`
    (a durable, due-in-the-future row) and delivers once released."""
    DELIVERED.clear()
    application = Application()
    db = ConnectionResolver()
    application.instance("db", db)
    queue = QueueManager(application, broker=InMemoryBroker(await_inplace=True))
    application.instance("queue", queue)
    mgr = NotificationManager(application)
    application.instance("notifications", mgr)
    set_application(application)
    QueuedJob.set_connection(db)
    await db.execute(sa.schema.CreateTable(QueuedJob.__table__))
    try:
        # a plain notifiable (not a Model) must be JSON-safe as-is — this rail really serializes.
        result = await mgr.later(0, "user-1", ReminderLater())
        assert result == {"queued": True}
        assert DELIVERED == []  # not yet — sitting in the jobs table
        released = await queue.release_due_jobs()
        assert released == 1
        assert DELIVERED == ["reminder"]  # delivered once released
    finally:
        set_application(None)
        await db.dispose()


class ScalarKeyedReminder(Notification, ShouldQueue):
    """The docs pattern: middleware() keys the limiter on a plain scalar captured in __init__,
    NOT on a model attribute — because SendQueuedNotification.middleware() runs before rehydration
    (self.<model> would still be a ref dict there). Keying on the scalar must survive the sync
    reconstruction (__new__ + __dict__.update restores __init__ attributes)."""

    def __init__(self, invoice_id: int) -> None:
        self.invoice_id = invoice_id

    def via(self, notifiable: Any) -> list[str]:
        return ["database"]

    def to_array(self, notifiable: Any) -> dict[str, Any]:
        return {"invoice": self.invoice_id}

    def middleware(self) -> list[Any]:
        return [
            RateLimited(
                RateLimiter(app().make("cache")), f"reminder:{self.invoice_id}", max_attempts=1
            )
        ]


async def test_middleware_keyed_on_an_init_scalar_survives_sync_reconstruction() -> None:
    # the queued job carries the notification ENCODED; SendQueuedNotification.middleware()
    # reconstructs it synchronously and calls middleware() — an __init__-set scalar must be intact
    # (this is the corrected docs pattern; the old model-attribute pattern crashed here).
    application = Application()
    CacheServiceProvider(application).register()
    set_application(application)
    try:
        job = SendQueuedNotification(object(), ScalarKeyedReminder(42), channels=["database"])
        mw = job.middleware()
        assert len(mw) == 1 and isinstance(mw[0], RateLimited)
        assert mw[0].key == "reminder:42"  # the scalar came through the reconstruction
    finally:
        set_application(None)
