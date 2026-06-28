"""Phase 11 — testkit: facade fakes + client factory."""

from __future__ import annotations

from typing import Any

import pytest

from arvel.mail import Mailable
from arvel.support.facades import Event, Mail, Queue
from arvel.testing import FakeEvents, FakeMailer, FakeQueue, client, fake, reset_fakes


class WelcomeMail(Mailable):
    def build(self) -> Mailable:
        return self.subject("Welcome")


class OrderPlaced:
    pass


@pytest.fixture(autouse=True)
def _reset() -> Any:
    yield
    reset_fakes()


async def test_mail_fake_records_sends() -> None:
    mailer = fake(Mail)
    assert isinstance(mailer, FakeMailer)
    await Mail.to("ada@example.com").send(WelcomeMail())
    mailer.assert_sent(WelcomeMail)


async def test_queue_fake_records_pushes() -> None:
    queue = fake(Queue)
    assert isinstance(queue, FakeQueue)
    await Queue.push(WelcomeMail, (), {})
    queue.assert_pushed(WelcomeMail)


async def test_events_fake_records_dispatch() -> None:
    events = fake(Event)
    assert isinstance(events, FakeEvents)
    await Event.dispatch(OrderPlaced())
    events.assert_dispatched(OrderPlaced)


def test_assert_nothing_helpers() -> None:
    fake(Mail).assert_nothing_sent()
    fake(Queue).assert_nothing_pushed()


def test_client_factory_serves() -> None:
    from arvel.http import HttpKernel

    kernel = HttpKernel()
    kernel.get("/ping", lambda request: {"ok": True})
    with client(kernel.build()) as http:
        assert http.get("/ping").json() == {"ok": True}
