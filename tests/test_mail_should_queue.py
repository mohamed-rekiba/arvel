"""Mail (doc 16/12) — a ShouldQueue mailable is enqueued, not sent inline, when a queue is bound."""

from __future__ import annotations

from email.message import EmailMessage
from typing import Any

from arvel.events import ShouldQueue
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

    async def push_instance(self, job: Any) -> None:
        self.pushed.append(job)


async def test_should_queue_mailable_is_enqueued() -> None:
    app = Application()
    mail = MailManager(app)
    app.instance("mail", mail)
    fake = FakeQueue()
    app.instance("queue", fake)
    set_application(app)
    try:
        sent = await mail.to("a@b.com").send(QueuedWelcome())
        assert sent is True
        assert len(fake.pushed) == 1
        job = fake.pushed[0]
        assert isinstance(job, SendQueuedMailable)
        assert job.recipients == ["a@b.com"]
        # nothing delivered inline
        assert mail.transport().sent == []  # type: ignore[attr-defined]
    finally:
        set_application(None)


async def test_plain_mailable_sends_inline_even_with_queue_bound() -> None:
    app = Application()
    mail = MailManager(app)
    app.instance("mail", mail)
    app.instance("queue", FakeQueue())
    set_application(app)
    try:
        await mail.to("a@b.com").send(Welcome())  # not ShouldQueue
        assert len(mail.transport().sent) == 1  # type: ignore[attr-defined]
    finally:
        set_application(None)


async def test_queued_job_handle_delivers() -> None:
    app = Application()
    mail = MailManager(app)
    app.instance("mail", mail)
    set_application(app)
    try:
        await SendQueuedMailable(["x@y.com"], QueuedWelcome()).handle()
        assert len(mail.transport().sent) == 1  # type: ignore[attr-defined]
    finally:
        set_application(None)
