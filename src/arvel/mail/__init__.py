"""arvel.mail — the Mail manager on **aiosmtplib** (mandated engine; DR-0002).

``log`` (records messages, no network) is the dev/test default; ``smtp`` sends via a
real ``aiosmtplib.SMTP`` (G4 — never a stdlib ``smtplib`` stand-in). ``Mailable`` is the
app's message class (``build()`` sets subject/body); ``Mail.to(user).send(MyMail())``.
aiosmtplib is imported lazily. Grounded in knowledge/port/16-managers.md.
"""

from __future__ import annotations

from email.message import EmailMessage
from typing import Any, Literal, cast

import msgspec

from arvel.kernel import Settings
from arvel.queue import Job
from arvel.support.manager import Manager

type Encryption = Literal["", "tls", "ssl"]  # "tls" = STARTTLS, "ssl" = implicit TLS, "" = none


class SmtpSettings(msgspec.Struct):
    """Typed view over the ``mail.smtp`` config section — host/port plus auth, encryption, timeout."""

    host: str = "localhost"
    port: int = 25
    username: str = ""
    password: str = ""
    encryption: Encryption = ""  # closed set → msgspec rejects anything else at load
    timeout: int = 30


class MailSettings(Settings):
    """Typed, validated view over the ``mail`` config section (DR-0016).

    ``MailSettings()`` reads + validates ``config("mail")`` — so a bad ``mail.smtp.port`` fails fast
    rather than surfacing as a connection error later.
    """

    __config_key__ = "mail"
    default: str = "log"
    smtp: SmtpSettings = msgspec.field(default_factory=SmtpSettings)


def _address(recipient: Any) -> str:
    return str(getattr(recipient, "email", recipient))


def _global_from() -> str:
    """The app-wide default sender (Laravel ``mail.from``): ``config('mail.from.address')`` formatted
    as ``Name <address>``. Applied when a mailable doesn't set ``from_`` — SMTP requires a From header,
    so without this a confirmation email built without an explicit sender fails to send."""
    from arvel.kernel import has_application

    if not has_application():
        return ""
    from arvel import config

    address = config("mail.from.address") or ""
    if not address:
        return ""
    name = config("mail.from.name") or ""
    return f"{name} <{address}>" if name else str(address)


class Mailable:
    """Base mail message: subclass and override ``build()`` (Laravel ``Mailable``)."""

    # Class-level defaults so the base fields exist even when a subclass defines its own ``__init__``
    # without calling ``super().__init__()`` (the normal Laravel shape) OR is rebuilt via
    # ``__new__`` (a queued mailable decoded by the worker — see SendQueuedMailable). Immutable
    # defaults are safe to share; the mutable attachment list is lazily created per-instance.
    _subject: str = ""
    _html: str = ""
    _from: str = ""  # sender address; defaults to the transport/agent if unset
    _reply_to: str = ""

    def __init__(self) -> None:
        self._attachments: list[tuple[bytes, str, str]] = []  # (data, filename, content-type)

    @property
    def _attachment_list(self) -> list[tuple[bytes, str, str]]:
        """The attachment list, lazily created — robust when ``__init__`` was bypassed/overridden."""
        attachments: list[tuple[bytes, str, str]] | None = self.__dict__.get("_attachments")
        if attachments is None:
            attachments = []
            self.__dict__["_attachments"] = attachments
        return attachments

    def subject(self, subject: str) -> Mailable:
        self._subject = subject
        return self

    def from_(self, address: Any) -> Mailable:
        """Set the sender (Laravel ``Mailable::from``). ``from_`` because ``from`` is a keyword."""
        self._from = _address(address)
        return self

    def reply_to(self, address: Any) -> Mailable:
        """Set the Reply-To address (Laravel ``Mailable::replyTo``)."""
        self._reply_to = _address(address)
        return self

    def html(self, body: str) -> Mailable:
        self._html = body
        return self

    def markdown(self, body: str) -> Mailable:
        """Set the body from Markdown, rendered to HTML (Laravel markdown mailables). Needs the
        ``markdown-it-py`` engine — the optional ``[mail]`` extra; raises if it isn't installed."""
        try:
            from markdown_it import MarkdownIt
        except ImportError as exc:
            from arvel.support.manager import MissingExtraError

            raise MissingExtraError("markdown", "mail") from exc
        self._html = MarkdownIt().render(body)
        return self

    def attach(self, path: str, *, name: str | None = None, mime: str | None = None) -> Mailable:
        """Attach a file from disk (Laravel ``->attach``); MIME is guessed from the name if omitted."""
        import mimetypes
        from pathlib import Path

        filename = name or Path(path).name
        ctype = mime or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        self._attachment_list.append((Path(path).read_bytes(), filename, ctype))
        return self

    def attach_data(
        self, data: bytes, name: str, *, mime: str = "application/octet-stream"
    ) -> Mailable:
        """Attach raw in-memory bytes as ``name`` (Laravel ``->attachData``)."""
        self._attachment_list.append((data, name, mime))
        return self

    def build(self) -> Mailable:  # overridden by subclasses
        return self

    def render(self) -> EmailMessage:
        self.build()
        message = EmailMessage()
        message["Subject"] = self._subject
        sender = self._from or _global_from()
        if sender:
            message["From"] = sender
        if self._reply_to:
            message["Reply-To"] = self._reply_to
        message.set_content(self._html, subtype="html")
        for data, filename, ctype in self._attachment_list:
            maintype, _, subtype = ctype.partition("/")
            message.add_attachment(
                data, maintype=maintype, subtype=subtype or "octet-stream", filename=filename
            )
        return message


class LogTransport:
    """A no-network transport that records sent messages (dev/test default)."""

    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    async def send(self, message: EmailMessage) -> bool:
        self.sent.append(message)
        return True


class SmtpTransport:
    """Sends via a real ``aiosmtplib.SMTP`` connection — a FRESH one per send.

    aiosmtplib clients are not concurrency-safe: when a queue worker executes two mail jobs at
    once, concurrent ``async with`` on a shared client collides on the session state and hangs
    until the SMTP timeout (caught live by the kit's queue-rail integration test). Each send
    opens its own connection (Laravel/Symfony mailer semantics)."""

    def __init__(self, config: SmtpSettings) -> None:
        self._config = config

    def _make_client(self) -> Any:
        import aiosmtplib

        config = self._config
        return aiosmtplib.SMTP(
            hostname=config.host,
            port=config.port,
            username=config.username or None,
            password=config.password or None,
            use_tls=config.encryption == "ssl",  # implicit TLS on connect
            start_tls=True if config.encryption == "tls" else None,  # STARTTLS, else auto
            timeout=config.timeout,
        )

    @property
    def client(self) -> Any:
        """A configured (unconnected) client — one per access, mirroring the per-send semantics."""
        return self._make_client()

    async def send(self, message: EmailMessage) -> bool:
        client = self._make_client()
        async with client:
            await client.send_message(message)
        return True


class SendQueuedMailable(Job):
    """Worker job that delivers a mailable enqueued via the ShouldQueue rail.

    The mailable is stored as a JSON-safe ``{class, state}`` view (``encode_instance``) rather than a
    live object, so the job survives serialization across a **real broker** (redis); the worker rebuilds
    it and runs ``build()`` there (Laravel semantics)."""

    def __init__(
        self,
        recipients: list[str],
        mailable: Mailable,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
    ) -> None:
        from arvel.queue import encode_instance

        self.recipients = recipients
        self.cc = cc or []
        self.bcc = bcc or []
        self.mailable = encode_instance(mailable)  # serializable repr (not the live Mailable)

    async def _rebuild_mailable(self) -> Mailable:
        """Reconstruct the Mailable from its encoded state (model attrs re-fetched fresh)."""
        from arvel.queue import decode_instance

        return cast("Mailable", await decode_instance(self.mailable))

    async def handle(self) -> bool:
        from arvel.kernel import app

        mailable = await self._rebuild_mailable()
        pending: PendingMail = app().make("mail").to(*self.recipients)
        pending.cc(*self.cc).bcc(*self.bcc)
        return await pending.send_now(mailable)


class PendingMail:
    """A pending send to a set of recipients (``Mail.to(...).cc(...).bcc(...).send(mailable)``)."""

    def __init__(self, mailer: MailManager, recipients: list[str]) -> None:
        self._mailer = mailer
        self._recipients = recipients
        self._cc: list[str] = []
        self._bcc: list[str] = []

    def cc(self, *recipients: Any) -> PendingMail:
        """Add carbon-copy recipients (Laravel ``->cc``)."""
        self._cc.extend(_address(r) for r in recipients)
        return self

    def bcc(self, *recipients: Any) -> PendingMail:
        """Add blind-carbon-copy recipients (Laravel ``->bcc``) — not shown to other recipients."""
        self._bcc.extend(_address(r) for r in recipients)
        return self

    async def send(self, mailable: Mailable) -> bool:
        """Deliver ``mailable`` — inline, or onto the queue when it's ``ShouldQueue`` and a
        queue is bound (the mail equivalent of the events ShouldQueue rail)."""
        from arvel.events import ShouldQueue

        app = self._mailer.app
        if (
            isinstance(mailable, ShouldQueue)
            and app is not None
            and hasattr(app, "bound")
            and app.bound("queue")
        ):
            job = SendQueuedMailable(self._recipients, mailable, self._cc, self._bcc)
            await app.make("queue").push_instance(job)
            return True
        return await self.send_now(mailable)

    async def send_now(self, mailable: Mailable) -> bool:
        """Deliver immediately, bypassing the queue rail (used by the worker job)."""
        message = mailable.render()
        message["To"] = ", ".join(self._recipients)
        if self._cc:
            message["Cc"] = ", ".join(self._cc)
        if self._bcc:
            # aiosmtplib strips Bcc from the wire but uses it for envelope recipients; the log
            # transport keeps it so tests can assert it.
            message["Bcc"] = ", ".join(self._bcc)
        result: bool = await self._mailer.transport().send(message)
        return result


class MailManager(Manager):
    """Resolves mail transports by config; ``to()`` opens a pending send."""

    def default_driver(self) -> str:
        return self._settings(MailSettings).default  # auto-loads + validates config("mail")

    def transport(self, name: str | None = None) -> Any:
        return self.driver(name)

    def to(self, *recipients: Any) -> PendingMail:
        return PendingMail(self, [_address(r) for r in recipients])

    def create_log_driver(self) -> LogTransport:
        return LogTransport()

    def create_smtp_driver(self) -> SmtpTransport:
        return SmtpTransport(self._settings(MailSettings).smtp)


__all__ = [
    "LogTransport",
    "MailManager",
    "MailSettings",
    "Mailable",
    "PendingMail",
    "SendQueuedMailable",
    "SmtpSettings",
    "SmtpTransport",
]
