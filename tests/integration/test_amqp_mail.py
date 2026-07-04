"""A queued Mailable survives a round-trip through a REAL AMQP broker.

In-process FakeQueue tests never serialize the job, so they'd miss a non-serializable queued mailable;
this exercises the real JSON-encode/decode path end to end.
"""

from __future__ import annotations

import asyncio
import contextlib

import pytest

from arvel import Application, Mail
from arvel.events import ShouldQueue
from arvel.kernel import set_application
from arvel.kernel.bootstrap import bootstrap_app
from arvel.mail import Mailable

pytestmark = pytest.mark.integration


class WelcomeQueuedMail(Mailable, ShouldQueue):
    """Carries state that must survive broker serialization."""

    def __init__(self, name: str) -> None:
        self.name = name

    def build(self) -> Mailable:
        return self.subject(f"Welcome, {self.name}").html(f"<p>Hello {self.name}</p>")


async def test_queued_mailable_round_trips_real_amqp_broker(rabbitmq_url: str) -> None:
    app = (
        Application.configure(".")
        .with_config(
            {
                "app": {"key": "base64:" + "A" * 43 + "=", "url": "http://test"},
                "mail": {"default": "log"},
                "queue": {"default": "amqp", "url": rabbitmq_url},
            }
        )
        .create()
    )
    try:
        bootstrap_app(app)
        await app.boot()

        await Mail.to("ada@example.com").send(WelcomeQueuedMail("Ada"))

        worker = asyncio.create_task(app.make("queue").work(release_interval=0.2))
        delivered = None
        for _ in range(150):  # up to ~15s for broker round-trip + delivery
            sent = app.make("mail").transport().sent
            if sent:
                delivered = sent[-1]
                break
            await asyncio.sleep(0.1)
        worker.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker

        assert delivered is not None, "queued mailable was not delivered after the AMQP round-trip"
        assert delivered["Subject"] == "Welcome, Ada"
        assert delivered["To"] == "ada@example.com"
    finally:
        with contextlib.suppress(Exception):
            await app.make("queue").broker.shutdown()
        set_application(None)
