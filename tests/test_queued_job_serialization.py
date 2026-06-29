"""Queued mail/notification jobs must survive serialization across a real broker.

These are the unit-level regression locks for the green-but-broken class an in-process FakeQueue
hides: ``serialize_instance`` must not raise (it would over redis/AMQP), and the worker's rebuild
(``__new__`` + restore state, bypassing ``__init__``) must still render/deliver.
"""

from __future__ import annotations

from arvel.events import ShouldQueue
from arvel.mail import Mailable, SendQueuedMailable
from arvel.notifications import Notification, SendQueuedNotification
from arvel.queue import decode_instance, deserialize_any, serialize_instance


class WelcomeMail(Mailable, ShouldQueue):
    """A queued mailable with its own __init__ (no super()) — the normal Laravel shape."""

    def __init__(self, name: str) -> None:
        self.name = name

    def build(self) -> Mailable:
        return self.subject(f"Hi {self.name}").html(f"<p>{self.name}</p>")


class WelcomeNotification(Notification):
    def __init__(self, name: str) -> None:
        self.name = name

    def to_array(self, notifiable: object) -> dict[str, str]:
        return {"name": self.name}


async def test_queued_mailable_serializes_and_rebuilds_renderable() -> None:
    job = SendQueuedMailable(["ada@example.com"], WelcomeMail("Ada"))
    payload = serialize_instance(job)  # must not raise (would, over a real broker, pre-fix)

    rebuilt = await deserialize_any(payload)
    mailable = await rebuilt._rebuild_mailable()  # __new__ + restore: no Mailable.__init__
    # the base fields exist via class-level defaults, so render() works despite the bypassed __init__
    message = mailable.render()
    assert message["Subject"] == "Hi Ada"
    assert mailable._from == ""  # class default, not an AttributeError
    assert mailable._attachment_list == []  # lazily created


async def test_queued_notification_serializes_and_rebuilds() -> None:
    job = SendQueuedNotification(notifiable=None, notification=WelcomeNotification("Ada"))
    payload = serialize_instance(
        job
    )  # was: msgspec TypeError "Encoding objects of type ... unsupported"

    rebuilt = await deserialize_any(payload)
    notification = await decode_instance(rebuilt.notification)
    assert isinstance(notification, WelcomeNotification)
    assert notification.name == "Ada"
