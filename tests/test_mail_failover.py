"""Entry 5.5 — failover + round-robin mail transports, composing existing drivers."""

from __future__ import annotations

from email.message import EmailMessage

import pytest

from arvel.kernel import Application, set_application
from arvel.mail import FailoverTransport, Mailable, MailManager, RoundRobinTransport


class _Welcome(Mailable):
    def build(self) -> Mailable:
        return self.subject("Hi").html("<p>hi</p>")


class _Recorder:
    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    async def send(self, message: EmailMessage) -> bool:
        self.sent.append(message)
        return True


class _Down:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def send(self, message: EmailMessage) -> bool:
        raise self._exc


async def test_failover_uses_the_first_healthy_transport() -> None:
    down = _Down(RuntimeError("connect refused"))
    up = _Recorder()
    transport = FailoverTransport([down, up])
    msg = EmailMessage()
    assert await transport.send(msg) is True
    assert up.sent == [msg]


async def test_failover_raises_the_last_error_when_all_are_down() -> None:
    first = _Down(RuntimeError("first down"))
    second = _Down(RuntimeError("second down"))
    transport = FailoverTransport([first, second])
    with pytest.raises(RuntimeError, match="second down"):
        await transport.send(EmailMessage())


async def test_round_robin_rotates_across_children() -> None:
    a, b = _Recorder(), _Recorder()
    transport = RoundRobinTransport([a, b])
    msg1, msg2, msg3 = EmailMessage(), EmailMessage(), EmailMessage()
    await transport.send(msg1)
    await transport.send(msg2)
    await transport.send(msg3)
    assert a.sent == [msg1, msg3]
    assert b.sent == [msg2]


async def test_manager_composes_failover_from_config() -> None:
    app = Application()
    app.make("config").set(
        "mail",
        {
            "default": "failover",
            "failover": {"mailers": ["smtp", "log"]},
            "smtp": {"host": "unreachable.invalid", "port": 1, "timeout": 1},
        },
    )
    mail = MailManager(app)
    app.instance("mail", mail)
    set_application(app)
    try:
        # smtp is unreachable → falls over to the log driver, still "sent"
        assert await mail.to("a@b.com").send_now(_Welcome()) is True
        assert len(mail.driver("log").sent) == 1
    finally:
        set_application(None)


async def test_manager_composes_round_robin_from_config() -> None:
    app = Application()
    app.make("config").set(
        "mail",
        {"default": "round_robin", "round_robin": {"mailers": ["log", "log"]}},
    )
    mail = MailManager(app)
    app.instance("mail", mail)
    set_application(app)
    try:
        driver = mail.transport()
        assert isinstance(driver, RoundRobinTransport)
        assert len(driver._transports) == 2
    finally:
        set_application(None)
