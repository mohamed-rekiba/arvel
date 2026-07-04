"""Queued mail/notification jobs must survive serialization across a real broker — an in-process
FakeQueue would hide a ``serialize_instance`` failure that only shows up over redis/AMQP."""

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
    payload = serialize_instance(job)  # must not raise (only surfaces over a real broker)

    rebuilt = await deserialize_any(payload)
    mailable = await rebuilt._rebuild_mailable()  # __new__ + restore: no Mailable.__init__
    # the base fields exist via class-level defaults, so render() works despite the bypassed __init__
    message = mailable.render()
    assert message["Subject"] == "Hi Ada"
    assert mailable._from == ""  # class default, not an AttributeError
    assert mailable._attachment_list == []  # lazily created


class MailWithAttachment(Mailable, ShouldQueue):
    def __init__(self) -> None:
        self.attach_data(b"\x89PNG\r\n\x1a\n binary", "logo.png", mime="image/png")

    def build(self) -> Mailable:
        return self.subject("Report").html("<p>see attached</p>")


async def test_queued_mailable_attachment_bytes_survive_serialization() -> None:
    # msgspec decodes to str without type info; model_ref/_rehydrate's bytes-tagging preserves bytes
    job = SendQueuedMailable(["ada@example.com"], MailWithAttachment())
    payload = serialize_instance(job)

    rebuilt = await deserialize_any(payload)
    mailable = await rebuilt._rebuild_mailable()
    data, name, mime = mailable._attachment_list[0]
    assert isinstance(data, bytes) and data == b"\x89PNG\r\n\x1a\n binary"
    assert (name, mime) == ("logo.png", "image/png")
    mailable.render()  # must not raise (a str attachment would crash add_attachment)


async def test_queued_notification_serializes_and_rebuilds() -> None:
    job = SendQueuedNotification(notifiable=None, notification=WelcomeNotification("Ada"))
    payload = serialize_instance(job)  # regression: msgspec can't encode a bare notification object

    rebuilt = await deserialize_any(payload)
    notification = await decode_instance(rebuilt.notification)
    assert isinstance(notification, WelcomeNotification)
    assert notification.name == "Ada"
