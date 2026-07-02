"""Mail typed settings — a typed, validated view over the ``mail`` config section (DR-0016)."""

from __future__ import annotations

from typing import Any

import msgspec
import pytest

from arvel.kernel import Application, set_application
from arvel.mail import MailManager, MailSettings, SmtpSettings, SmtpTransport


def _app(**mail: Any) -> Application:
    app = Application()
    app.make("config").set("mail", mail)
    set_application(app)
    return app


def test_defaults_without_an_app() -> None:
    set_application(None)
    s = MailSettings()
    assert s.default == "log"
    assert (s.smtp.host, s.smtp.port) == ("localhost", 25)


def test_reads_and_validates_the_config_section() -> None:
    _app(
        default="smtp",
        smtp={
            "host": "mail.example",
            "port": "587",
            "username": "postmaster",
            "password": "s3cret",
            "encryption": "tls",
            "timeout": "20",
        },
    )
    try:
        s = MailSettings()
        assert s.default == "smtp"
        assert s.smtp.host == "mail.example"
        assert s.smtp.port == 587  # coerced str → int (nested struct)
        assert s.smtp.username == "postmaster"
        assert s.smtp.encryption == "tls"
        assert s.smtp.timeout == 20  # coerced
    finally:
        set_application(None)


def test_invalid_encryption_value_is_rejected() -> None:
    _app(smtp={"encryption": "bogus"})  # not in the Literal set
    try:
        with pytest.raises(msgspec.ValidationError):
            MailSettings()
    finally:
        set_application(None)


def test_smtp_defaults_are_unauthenticated_plaintext() -> None:
    set_application(None)
    s = MailSettings().smtp
    assert (s.username, s.password, s.encryption) == ("", "", "")  # no auth/TLS by default


def test_smtp_transport_applies_auth_and_encryption() -> None:
    cfg = SmtpSettings(host="h", port=465, username="u", password="p", encryption="ssl")
    t = SmtpTransport(cfg)
    assert (t._config.username, t._config.password) == ("u", "p")  # credentials carried
    assert t.client.use_tls is True  # encryption="ssl" → implicit TLS wired into the client


async def test_concurrent_sends_use_independent_connections() -> None:
    """One SmtpTransport, N concurrent sends → N independent SMTP connections. aiosmtplib clients
    are not concurrency-safe: a shared client deadlocks when a worker executes two queued mail
    jobs at once (caught live by the kit's queue-rail integration test — the mail jobs hung until
    the SMTP timeout while the shared client's session state collided)."""
    import asyncio
    from email.message import EmailMessage

    used_clients: list[Any] = []

    class _FakeSmtp:
        def __init__(self) -> None:
            used_clients.append(self)
            self.sent: list[Any] = []

        async def __aenter__(self) -> "_FakeSmtp":
            await asyncio.sleep(0.01)  # force overlap between the two sends
            return self

        async def __aexit__(self, *exc: Any) -> None:
            return None

        async def send_message(self, message: Any) -> None:
            await asyncio.sleep(0.01)
            self.sent.append(message)

    transport = SmtpTransport(SmtpSettings(host="h", port=25))
    transport._make_client = lambda: _FakeSmtp()  # type: ignore[method-assign]

    msg1, msg2 = EmailMessage(), EmailMessage()
    assert await asyncio.gather(transport.send(msg1), transport.send(msg2)) == [True, True]
    assert len(used_clients) == 2  # a fresh connection per send — never a shared session
    assert [len(c.sent) for c in used_clients] == [1, 1]


def test_invalid_port_fails_fast() -> None:
    _app(smtp={"port": "not-a-number"})
    try:
        with pytest.raises(msgspec.ValidationError):
            MailSettings()
    finally:
        set_application(None)


def test_manager_default_driver_uses_settings() -> None:
    _app(default="smtp")
    try:
        assert MailManager().default_driver() == "smtp"
    finally:
        set_application(None)


def test_smtp_transport_takes_typed_settings() -> None:
    t = SmtpTransport(SmtpSettings(host="smtp.example", port=2525))
    assert t._config.host == "smtp.example"
    assert t._config.port == 2525
