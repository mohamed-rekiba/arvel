"""arvel.mail — the Mail manager on **aiosmtplib** (mandated engine; DR-0002).

``log`` (records messages, no network) is the dev/test default; ``smtp`` sends via a
real ``aiosmtplib.SMTP`` (G4 — never a stdlib ``smtplib`` stand-in). ``Mailable`` is the
app's message class (``build()`` sets subject/body); ``Mail.to(user).send(MyMail())``.
aiosmtplib is imported lazily. Grounded in knowledge/port/16-managers.md.
"""

from __future__ import annotations

import re
from email.message import EmailMessage
from enum import StrEnum
from html.parser import HTMLParser
from typing import TYPE_CHECKING, Any, Literal, cast

if TYPE_CHECKING:
    from pathlib import Path

import msgspec

from arvel.kernel import Settings
from arvel.queue import Job
from arvel.support.manager import Manager

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

type Encryption = Literal["", "tls", "ssl"]  # "tls" = STARTTLS, "ssl" = implicit TLS, "" = none


class SmtpSettings(msgspec.Struct):
    """Typed view over the ``mail.smtp`` config section — host/port plus auth, encryption, timeout."""

    host: str = "localhost"
    port: int = 25
    username: str = ""
    password: str = ""
    encryption: Encryption = ""  # closed set → msgspec rejects anything else at load
    timeout: int = 30


class MailerListSettings(msgspec.Struct):
    """Typed view over a composed mailer's ``mailers`` list — the child driver names
    ``failover``/``round_robin`` resolve through this SAME registry (``mail.failover.mailers``,
    ``mail.round_robin.mailers``), so their config is reused rather than duplicated."""

    mailers: list[str] = msgspec.field(default_factory=list[str])


class MailDriver(StrEnum):
    """The built-in mail transports — a typed set for ``mail.default``. A ``StrEnum`` (not a
    ``Literal``): flows through the string-keyed driver dispatch, so a custom transport registered
    via ``MailManager.extend`` stays a plain ``str`` — the registry stays open."""

    SMTP = "smtp"
    LOG = "log"
    FAILOVER = "failover"
    ROUND_ROBIN = "round_robin"


class MailSettings(Settings):
    """Typed, validated view over the ``mail`` config section (DR-0016).

    ``MailSettings()`` reads + validates ``config("mail")`` — so a bad ``mail.smtp.port`` fails fast
    rather than surfacing as a connection error later.
    """

    __config_key__ = "mail"
    default: str = "log"
    smtp: SmtpSettings = msgspec.field(default_factory=SmtpSettings)
    failover: MailerListSettings = msgspec.field(default_factory=MailerListSettings)
    round_robin: MailerListSettings = msgspec.field(default_factory=MailerListSettings)


def _address(recipient: Any) -> str:
    return str(getattr(recipient, "email", recipient))


class _TagStripper(HTMLParser):
    """Collects text data, turning block-level tags into line breaks — used to auto-derive a
    readable plain-text alternative from an HTML body."""

    _BLOCK_TAGS = frozenset(
        {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote"}
    )

    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        self._chunks.append(data)

    def text(self) -> str:
        collapsed = re.sub(r"\n{2,}", "\n\n", "".join(self._chunks))
        return collapsed.strip()


def _strip_tags(html_body: str) -> str:
    """A readable plain-text derivation from an HTML body (block tags become line breaks) — the
    text/plain alternative a ``Mailable`` gets for free when it sets only ``html()``/``markdown()``
    (no explicit ``text()``); mail deliverability wants both parts (spec 19)."""
    stripper = _TagStripper()
    stripper.feed(html_body)
    stripper.close()
    return stripper.text()


def _global_from() -> str:
    """The app-wide default sender: ``config('mail.from.address')`` formatted
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


class _StorageRef:
    """A deferred attachment read from a storage disk — loaded off the loop in
    ``resolve_attachments`` (the disk's ``get`` is async), never in the sync ``render``."""

    __slots__ = ("disk", "path")

    def __init__(self, disk: Any, path: str) -> None:
        self.disk = disk
        self.path = path


class Mailable:
    """Base mail message: subclass and override ``build()``."""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        # A queued mailable crosses the broker as a class ref plus state, and that ref is
        # attacker-settable on a tampered payload — so the worker resolves it from this registry
        # instead of importing the name it was handed (GH-301).
        from arvel.queue.serialization import register_serializable

        super().__init_subclass__(**kwargs)
        register_serializable(cls)

    # Class-level defaults so base fields exist even if a subclass skips super().__init__() or is
    # rebuilt via __new__ (a queued mailable decoded by the worker; see SendQueuedMailable).
    _subject: str = ""
    _html: str = ""
    _text: str = ""  # explicit plain-text alternative; auto-derived from _html when unset
    _from: str = ""  # sender address; defaults to the transport/agent if unset
    _reply_to: str = ""

    def __init__(self) -> None:
        self._attachments: list[tuple[bytes, str, str]] = []  # (data, filename, content-type)

    @property
    def _attachment_list(self) -> list[tuple[bytes | Path | _StorageRef, str, str]]:
        """The attachment list, lazily created — robust when ``__init__`` was bypassed/overridden."""
        attachments: list[tuple[bytes | Path | _StorageRef, str, str]] | None = self.__dict__.get(
            "_attachments"
        )
        if attachments is None:
            attachments = []
            self.__dict__["_attachments"] = attachments
        return attachments

    @property
    def _inline_list(self) -> list[tuple[bytes | Path | _StorageRef, str, str]]:
        """Inline (``cid:``) images, lazily created — ``(data, content-id, content-type)``."""
        inline: list[tuple[bytes | Path | _StorageRef, str, str]] | None = self.__dict__.get(
            "_inline"
        )
        if inline is None:
            inline = []
            self.__dict__["_inline"] = inline
        return inline

    def subject(self, subject: str) -> Mailable:
        self._subject = subject
        return self

    def from_(self, address: Any) -> Mailable:
        """Set the sender. ``from_`` because ``from`` is a keyword."""
        self._from = _address(address)
        return self

    def reply_to(self, address: Any) -> Mailable:
        """Set the Reply-To address."""
        self._reply_to = _address(address)
        return self

    def html(self, body: str) -> Mailable:
        self._html = body
        return self

    def text(self, body: str) -> Mailable:
        """Set an explicit plain-text alternative. Without this, one
        is auto-derived from the HTML body by stripping tags — this only overrides that default."""
        self._text = body
        return self

    def markdown(self, body: str) -> Mailable:
        """Set the body from Markdown, rendered through the component theme — styled buttons
        (``[button: Text](url)``), panels (blockquotes), and tables, not raw md→html. Needs the
        ``markdown-it-py`` engine — the optional ``[mail]`` extra;
        raises if it isn't installed."""
        try:
            from markdown_it import MarkdownIt
        except ImportError as exc:
            from arvel.support.manager import MissingExtraError

            raise MissingExtraError("markdown", "mail") from exc
        from arvel.mail.markdown_theme import render_themed

        self._html = render_themed(body, MarkdownIt)
        return self

    def attach(self, path: str, *, name: str | None = None, mime: str | None = None) -> Mailable:
        """Attach a file from disk; MIME is guessed from the name if omitted. The read is
        deferred: the async send path loads it off the event loop, so building a mailable
        in a request handler never blocks on disk I/O."""
        import mimetypes
        from pathlib import Path

        filename = name or Path(path).name
        ctype = mime or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        self._attachment_list.append((Path(path), filename, ctype))
        return self

    def attach_from_storage(
        self, disk: Any, path: str, *, name: str | None = None, mime: str | None = None
    ) -> Mailable:
        """Attach a file living on a storage ``disk`` (``Storage.disk("s3")`` etc.). The disk read
        is deferred to the async send path (off the event loop), like :meth:`attach`."""
        import mimetypes

        filename = name or path.rsplit("/", 1)[-1]
        ctype = mime or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        self._attachment_list.append((_StorageRef(disk, path), filename, ctype))
        return self

    def embed(self, path: str, *, mime: str | None = None) -> str:
        """Embed a local image inline and return its ``cid:`` reference for the HTML body, e.g.
        ``html(f'<img src="{mail.embed("logo.png")}">')``. The read is deferred to the send path."""
        import mimetypes
        from pathlib import Path

        cid = self._new_cid()
        ctype = mime or mimetypes.guess_type(path)[0] or "application/octet-stream"
        self._inline_list.append((Path(path), cid, ctype))
        return f"cid:{cid}"

    def embed_data(self, data: bytes, *, mime: str) -> str:
        """Embed raw image bytes inline; returns the ``cid:`` reference for the HTML body."""
        cid = self._new_cid()
        self._inline_list.append((data, cid, mime))
        return f"cid:{cid}"

    @staticmethod
    def _new_cid() -> str:
        from arvel.support import Str

        return f"{Str.uuid()}@arvel"

    async def resolve_attachments(self) -> None:
        """Load any deferred attachments/inline images into memory off the event loop — a local
        path via a worker thread, a storage ref via the disk's async ``get``. Called by the send
        path before ``render()``; idempotent."""
        self._attachment_list[:] = [
            (await self._load(data), name, ctype) for data, name, ctype in self._attachment_list
        ]
        self._inline_list[:] = [
            (await self._load(data), cid, ctype) for data, cid, ctype in self._inline_list
        ]

    @staticmethod
    async def _load(data: bytes | Path | _StorageRef) -> bytes:
        from pathlib import Path

        from anyio.to_thread import run_sync

        if isinstance(data, _StorageRef):
            return cast("bytes", await data.disk.get(data.path))
        if isinstance(data, Path):
            return await run_sync(data.read_bytes)
        return data

    def attach_data(
        self, data: bytes, name: str, *, mime: str = "application/octet-stream"
    ) -> Mailable:
        """Attach raw in-memory bytes as ``name``."""
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
        # Always multipart/alternative (deliverability, spec 19): the text part first, then HTML —
        # add_alternative's LAST part is a mail client's preferred one, so HTML still renders when
        # both are supported, while a text-only client (or a spam filter) still gets real content.
        message.set_content(self._text or _strip_tags(self._html), subtype="plain")
        message.add_alternative(self._html, subtype="html")

        # Inline images ride on the HTML alternative as multipart/related parts, keyed by Content-ID
        # so the body's `cid:...` refs resolve. Must attach before the regular attachments below.
        if self._inline_list:
            html_part = cast("EmailMessage", message.get_body(preferencelist=("html",)))
            for data, cid, ctype in self._inline_list:
                maintype, _, subtype = ctype.partition("/")
                html_part.add_related(
                    self._render_bytes(data),
                    maintype=maintype,
                    subtype=subtype or "octet-stream",
                    cid=f"<{cid}>",
                )

        for data, filename, ctype in self._attachment_list:
            maintype, _, subtype = ctype.partition("/")
            message.add_attachment(
                self._render_bytes(data),
                maintype=maintype,
                subtype=subtype or "octet-stream",
                filename=filename,
            )
        return message

    @staticmethod
    def _render_bytes(data: bytes | Path | _StorageRef) -> bytes:
        from pathlib import Path

        if isinstance(data, Path):  # direct sync render() (tests) — send paths pre-resolve
            return data.read_bytes()
        if isinstance(data, _StorageRef):
            raise RuntimeError(
                "a storage attachment needs the async send path; call resolve_attachments() first"
            )
        return data


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
    opens its own connection."""

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
        """A configured (unconnected) client — a FRESH instance per access (non-identity-stable),
        mirroring the per-send connection semantics."""
        return self._make_client()

    async def send(self, message: EmailMessage) -> bool:
        client = self._make_client()
        async with client:
            await client.send_message(message)
        return True


class FailoverTransport:
    """Tries child transports in order, moving to the next on a connect/send error; all down
    → re-raises the last error. Children are resolved driver instances (``mail.failover.mailers``),
    so this composes existing transports rather than knowing about SMTP/log itself."""

    def __init__(self, transports: list[Any]) -> None:
        self._transports = transports

    async def send(self, message: EmailMessage) -> bool:
        last_error: Exception | None = None
        for transport in self._transports:
            try:
                result: bool = await transport.send(message)
            except Exception as exc:  # a down mailer must not stop the failover walk
                last_error = exc
                continue
            return result
        if last_error is not None:
            raise last_error
        raise RuntimeError("mail.failover: no mailers configured")


class RoundRobinTransport:
    """Rotates across child transports, one per send — spreads load, no failure fallback (pair
    with ``failover`` for that). Children are resolved driver instances (``mail.round_robin.mailers``)."""

    def __init__(self, transports: list[Any]) -> None:
        self._transports = transports
        self._next = 0

    async def send(self, message: EmailMessage) -> bool:
        if not self._transports:
            raise RuntimeError("mail.round_robin: no mailers configured")
        transport = self._transports[self._next % len(self._transports)]
        self._next += 1
        result: bool = await transport.send(message)
        return result


class SendQueuedMailable(Job):
    """Worker job that delivers a mailable enqueued via the ShouldQueue rail.

    The mailable is stored as a JSON-safe ``{class, state}`` view (``encode_instance``) rather than a
    live object, so the job survives serialization across a **real broker** (redis); the worker rebuilds
    it and runs ``build()`` there."""

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
        """Add carbon-copy recipients."""
        self._cc.extend(_address(r) for r in recipients)
        return self

    def bcc(self, *recipients: Any) -> PendingMail:
        """Add blind-carbon-copy recipients — not shown to other recipients."""
        self._bcc.extend(_address(r) for r in recipients)
        return self

    async def send(self, mailable: Mailable) -> bool:
        """Deliver ``mailable`` — inline, or onto the queue when it's ``ShouldQueue`` and a
        queue is bound (the mail equivalent of the events ShouldQueue rail). The enqueue itself
        rides the same after-commit seam as a queued job: buffered while a transaction is open
        (dropped on rollback), immediate outside one."""
        from arvel.events import ShouldQueue

        app = self._mailer.app
        if (
            isinstance(mailable, ShouldQueue)
            and app is not None
            and hasattr(app, "bound")
            and app.bound("queue")
        ):
            job = SendQueuedMailable(self._recipients, mailable, self._cc, self._bcc)
            queue = app.make("queue")
            await self._after_commit(lambda: queue.push_instance(job))
            return True
        return await self.send_now(mailable)

    async def later(self, delay: float, mailable: Mailable) -> bool:
        """Queue ``mailable`` to send after ``delay`` seconds via the queue's durable delayed-dispatch
        path (``dispatch_after``) — regardless of ``ShouldQueue``. Same after-commit semantics as
        :meth:`send`. Falls back to an immediate send when no queue is bound (there's nothing to
        delay against)."""
        app = self._mailer.app
        if not (app is not None and hasattr(app, "bound") and app.bound("queue")):
            return await self.send_now(mailable)
        job = SendQueuedMailable(self._recipients, mailable, self._cc, self._bcc)
        queue = app.make("queue")
        await self._after_commit(lambda: queue.dispatch_after(delay, job))
        return True

    async def _after_commit(self, callback: Callable[[], Awaitable[Any]]) -> Any:
        """Route ``callback`` through the events after-commit buffer — the SAME seam
        ``QueueManager._defer_to_commit`` uses for a plain ``Job.dispatch()``: buffered while a
        transaction is open (dropped on rollback), run immediately outside one/without an events
        dispatcher bound."""
        app = self._mailer.app
        if app is not None and hasattr(app, "bound") and app.bound("events"):
            return await app.make("events").after_commit(callback)
        return await callback()

    async def send_now(self, mailable: Mailable) -> bool:
        """Deliver immediately, bypassing the queue rail (used by the worker job)."""
        await mailable.resolve_attachments()  # disk reads happen off the loop, not in render()
        message = mailable.render()
        message["To"] = ", ".join(self._recipients)
        if self._cc:
            message["Cc"] = ", ".join(self._cc)
        if self._bcc:
            # Stripped from the wire by aiosmtplib; kept here so the log transport lets tests assert it.
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

    def create_failover_driver(self) -> FailoverTransport:
        names = self._settings(MailSettings).failover.mailers
        return FailoverTransport([self.transport(name) for name in names])

    def create_round_robin_driver(self) -> RoundRobinTransport:
        names = self._settings(MailSettings).round_robin.mailers
        return RoundRobinTransport([self.transport(name) for name in names])


__all__ = [
    "FailoverTransport",
    "LogTransport",
    "MailDriver",
    "MailManager",
    "MailSettings",
    "Mailable",
    "MailerListSettings",
    "PendingMail",
    "RoundRobinTransport",
    "SendQueuedMailable",
    "SmtpSettings",
    "SmtpTransport",
]
