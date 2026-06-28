"""Mail (doc 16) — recipient + sender parity: Mailable.from_/reply_to set From/Reply-To headers;
PendingMail.cc/bcc add Cc/Bcc (Laravel Mail::to(...)->cc(...)->bcc(...)). Previously only `to` existed
and the rendered message carried no From/Reply-To."""

from __future__ import annotations

from arvel.mail import LogTransport, Mailable, PendingMail, SendQueuedMailable


class Doc(Mailable):
    def build(self) -> Mailable:
        return self.subject("Hi").html("<p>x</p>")


class WelcomeMail(Mailable):
    """A mailable with subclass state — module-level so the queue's class loader can import it back."""

    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name

    def build(self) -> Mailable:
        return self.subject(f"Welcome {self.name}").html("<p>hi</p>")


class _Mailer:
    """Minimal mailer for PendingMail: exposes transport() + app (the send_now path uses both)."""

    def __init__(self) -> None:
        self.app = None
        self._t = LogTransport()

    def transport(self) -> LogTransport:
        return self._t


def test_render_sets_from_and_reply_to() -> None:
    message = Doc().from_("sender@x.com").reply_to("help@x.com").render()
    assert message["From"] == "sender@x.com"
    assert message["Reply-To"] == "help@x.com"


def test_render_omits_sender_headers_when_unset() -> None:
    message = Doc().render()
    assert message["From"] is None and message["Reply-To"] is None


def test_from_accepts_an_object_with_email() -> None:
    class U:
        email = "u@x.com"

    assert Doc().from_(U()).render()["From"] == "u@x.com"


async def test_to_cc_bcc_become_headers() -> None:
    mailer = _Mailer()
    pending = PendingMail(mailer, ["to@x.com"]).cc("cc@x.com").bcc("bcc@x.com")  # type: ignore[arg-type]
    await pending.send_now(Doc())
    msg = mailer._t.sent[0]
    assert msg["To"] == "to@x.com"
    assert msg["Cc"] == "cc@x.com"
    assert msg["Bcc"] == "bcc@x.com"  # log transport keeps Bcc for inspection


async def test_cc_bcc_are_chainable_and_multi() -> None:
    mailer = _Mailer()
    pending = PendingMail(mailer, ["a@x.com", "b@x.com"]).cc("c@x.com", "d@x.com")  # type: ignore[arg-type]
    await pending.send_now(Doc())
    msg = mailer._t.sent[0]
    assert msg["To"] == "a@x.com, b@x.com"
    assert msg["Cc"] == "c@x.com, d@x.com"
    assert msg["Bcc"] is None  # none added → no header


async def test_no_cc_bcc_leaves_only_to() -> None:
    mailer = _Mailer()
    await PendingMail(mailer, ["to@x.com"]).send_now(Doc())  # type: ignore[arg-type]
    msg = mailer._t.sent[0]
    assert msg["To"] == "to@x.com" and msg["Cc"] is None and msg["Bcc"] is None


def test_queued_mailable_carries_cc_and_bcc() -> None:
    job = SendQueuedMailable(["to@x.com"], Doc(), ["cc@x.com"], ["bcc@x.com"])
    assert job.cc == ["cc@x.com"] and job.bcc == ["bcc@x.com"]  # preserved onto the queue


async def test_queued_mailable_survives_broker_serialization_and_rebuilds() -> None:
    """Regression: SendQueuedMailable used to hold a live Mailable, which msgspec can't encode — so
    queued mail broke over a real (redis) broker while the in-process test queue passed. Now the
    mailable is stored as a JSON-safe class+state view and rebuilt (build() runs) in the worker."""
    from arvel.queue import deserialize_instance, serialize_instance

    job = SendQueuedMailable(["to@x.com"], WelcomeMail("Ada"), ["cc@x.com"])
    payload = serialize_instance(job)  # the exact broker path — must NOT raise TypeError
    assert isinstance(payload, str)

    restored = await deserialize_instance(payload)
    assert restored.recipients == ["to@x.com"] and restored.cc == ["cc@x.com"]

    mailable = await restored._rebuild_mailable()
    msg = mailable.render()
    assert msg["Subject"] == "Welcome Ada"  # subclass state survived; build() ran on rebuild
