"""Entry 5.1 — queued mail respects the surrounding DB transaction: the enqueue rides the
SAME after-commit seam a queued job uses (``events.after_commit``, opened by ``db.transaction()``),
so a rollback drops it and a commit fires it exactly once. ``later()`` schedules a delayed send via
the queue's durable ``dispatch_after`` regardless of ``ShouldQueue``."""

from __future__ import annotations

from email.message import EmailMessage
from typing import Any

import pytest

from arvel.database.connections import ConnectionResolver
from arvel.events import Dispatcher, ShouldQueue
from arvel.kernel import Application, set_application
from arvel.mail import Mailable, MailManager, SendQueuedMailable


class Welcome(Mailable):
    def render(self) -> EmailMessage:
        msg = EmailMessage()
        msg["Subject"] = "Welcome"
        msg.set_content("hi")
        return msg


class QueuedWelcome(Welcome, ShouldQueue):
    pass


class FakeQueue:
    def __init__(self) -> None:
        self.pushed: list[Any] = []
        self.delayed: list[tuple[float, Any]] = []

    async def push_instance(self, job: Any) -> None:
        self.pushed.append(job)

    async def dispatch_after(self, delay: float, job: Any) -> None:
        self.delayed.append((delay, job))


class Boom(Exception):
    pass


@pytest.fixture
async def ctx() -> Any:
    app = Application()
    events = Dispatcher()
    queue = FakeQueue()
    app.instance("events", events)
    app.instance("queue", queue)
    mail = MailManager(app)
    app.instance("mail", mail)
    set_application(app)
    db = ConnectionResolver({"default": {"url": "sqlite+aiosqlite://"}})
    try:
        yield app, queue, mail, db
    finally:
        set_application(None)
        await db.dispose()


async def test_rollback_drops_the_queued_send(ctx: Any) -> None:
    _app, queue, mail, db = ctx
    with pytest.raises(Boom):
        async with db.transaction():
            await mail.to("a@b.com").send(QueuedWelcome())
            assert queue.pushed == []  # buffered, not yet enqueued
            raise Boom
    assert queue.pushed == []  # rollback drops it


async def test_commit_enqueues_exactly_once(ctx: Any) -> None:
    _app, queue, mail, db = ctx
    async with db.transaction():
        sent = await mail.to("a@b.com").send(QueuedWelcome())
        assert sent is True
        assert queue.pushed == []  # not yet — still inside the transaction
    assert len(queue.pushed) == 1
    job = queue.pushed[0]
    assert isinstance(job, SendQueuedMailable)
    assert job.recipients == ["a@b.com"]


async def test_outside_a_transaction_the_enqueue_is_immediate() -> None:
    app = Application()
    events = Dispatcher()
    queue = FakeQueue()
    app.instance("events", events)
    app.instance("queue", queue)
    mail = MailManager(app)
    app.instance("mail", mail)
    set_application(app)
    try:
        await mail.to("a@b.com").send(QueuedWelcome())
        assert len(queue.pushed) == 1
    finally:
        set_application(None)


async def test_later_schedules_a_delayed_send_regardless_of_should_queue(ctx: Any) -> None:
    _app, queue, mail, _db = ctx
    ok = await mail.to("a@b.com").later(30, Welcome())  # not ShouldQueue
    assert ok is True
    assert len(queue.delayed) == 1
    delay, job = queue.delayed[0]
    assert delay == 30
    assert isinstance(job, SendQueuedMailable)


async def test_later_inside_a_rolled_back_transaction_is_dropped(ctx: Any) -> None:
    _app, queue, mail, db = ctx
    with pytest.raises(Boom):
        async with db.transaction():
            await mail.to("a@b.com").later(10, Welcome())
            raise Boom
    assert queue.delayed == []
