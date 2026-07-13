"""Coverage — mail manager, log manager, attribute detection (docs 16/01/07)."""

from __future__ import annotations

import aiosmtplib

from arvel.database.attribute import Attribute, returns_attribute
from arvel.kernel.logging import LogManager, configure_logging
from arvel.mail import LogTransport, Mailable, MailManager


class Welcome(Mailable):
    def build(self) -> Mailable:
        return self.subject("Hi").html("<p>hello</p>")


async def test_mail_log_transport_default() -> None:
    manager = MailManager()
    assert manager.default_driver() == "log"
    await manager.to("ada@example.com").send(Welcome())
    transport = manager.transport()
    assert isinstance(transport, LogTransport)
    assert transport.sent[0]["Subject"] == "Hi"


def test_mail_smtp_transport_builds() -> None:
    transport = MailManager().driver("smtp")
    assert isinstance(transport.client, aiosmtplib.SMTP)


def test_log_manager_levels_and_binding() -> None:
    configure_logging(json_logs=True)
    log = LogManager()
    log.debug("d")
    log.info("i")
    log.warning("w")
    log.error("e")
    log.critical("c")
    assert isinstance(log.channel("payments"), LogManager)
    assert isinstance(log.bind(request_id="r1"), LogManager)
    configure_logging(json_logs=False)  # restore console renderer


def test_json_logs_render_structured_tracebacks_without_locals() -> None:
    """In prod (JSON) mode an exc_info renders as a structured ``exception`` field (frame list) — so
    aggregators can parse it — but WITHOUT frame locals, so a sensitive value living in a local does
    not leak into logs (rule 20-security). Exercised via LogManager (the prod path)."""
    import contextlib
    import io
    import json

    configure_logging(json_logs=True)
    try:
        buf = io.StringIO()
        canary = "leak-canary-9f3a2"  # a frame local that must NOT appear in the log output
        with contextlib.redirect_stdout(buf):
            log = LogManager().channel("http")
            try:
                _local = canary  # deliberately a frame local in the raising frame
                raise ValueError("boom")
            except ValueError:
                log.error("request_failed", exc_info=True)
        output = buf.getvalue()
        record = json.loads(output.strip().splitlines()[-1])
        assert record["event"] == "request_failed"
        exc = record["exception"][0]
        assert exc["exc_type"] == "ValueError"
        assert exc["frames"]  # structured frames are present
        assert "locals" not in exc["frames"][0]  # but frame locals are excluded
        assert canary not in output  # the sensitive local did not leak
    finally:
        configure_logging(json_logs=False)


def test_returns_attribute_detection() -> None:
    def accessor() -> Attribute:  # annotation is the Attribute (string under future-annotations)
        return Attribute()

    def other() -> int:
        return 1

    def untyped():
        return 1

    assert returns_attribute(accessor)
    assert not returns_attribute(other)
    assert not returns_attribute(untyped)
