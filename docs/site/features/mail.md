# Mail

<a name="introduction"></a>
## Introduction

Sending email doesn't have to be complicated. Arvel provides a clean, simple email API powered by **mailables** — small classes that describe a single message. Each mailable defines its envelope (sender, recipient, subject), its content (HTML and/or plain-text body), and any attachments. The `Mail` facade then renders and delivers it through a configured driver.

<a name="quick-start"></a>
### Quick start

Register the provider, point the driver at `log` for local dev, define a mailable, send:

```python
# bootstrap/providers.py
from arvel.mail.providers.mail_service_provider import MailServiceProvider

providers = [MailServiceProvider, ...]
```

```ini
# .env — local dev: rendered messages go to the log
MAIL_DEFAULT=log
MAIL_FROM_ADDRESS=hello@example.com
MAIL_FROM_NAME="Arvel App"
```

```python
from arvel.facades.mail import Mail
from arvel.mail.content import Content
from arvel.mail.envelope import Envelope
from arvel.mail.mailable import Mailable


class WelcomeMail(Mailable):
    def envelope(self) -> Envelope:
        return Envelope(to=["user@example.com"], subject="Welcome!")

    def content(self) -> Content:
        return Content(html="<p>Thanks for signing up.</p>")


await Mail.to("user@example.com").send(WelcomeMail())
```

`Mail.to()` accepts an email string or any object with an `.email` attribute. Override recipients with the fluent chain — `send()` renders the mailable and delivers through the active driver.

| Piece | Responsibility |
|---|---|
| `envelope()` | To, subject, optional from/cc/bcc — [Configuring the envelope](#configuring-the-envelope) |
| `content()` | Inline HTML/text or Jinja2 views — [Configuring the content](#configuring-the-content) |
| `attachments()` | Optional files — [Attachments](#attachments) |
| Tests | `with Mail.fake() as mailbox:` — [Testing](#testing) |

<a name="configuration"></a>
## Configuration

Mail is configured through `MailConfig` (the `MAIL_*` environment variables):

```ini
MAIL_DEFAULT=smtp
MAIL_FROM_ADDRESS=hello@example.com
MAIL_FROM_NAME="Arvel App"

# SMTP driver settings (prefixed MAIL_SMTP_)
MAIL_SMTP_HOST=smtp.example.com
MAIL_SMTP_PORT=587
MAIL_SMTP_USERNAME=postmaster@example.com
MAIL_SMTP_PASSWORD=secret
MAIL_SMTP_ENCRYPTION=tls
```

`MAIL_DEFAULT` picks the driver (`log`, `array`, or `smtp`). SMTP-specific settings live under the `MAIL_SMTP_` prefix.

<a name="drivers"></a>
### Drivers

| Driver | Behavior |
|---|---|
| `log` | Writes the rendered message to the log — good for local development |
| `array` | Captures messages in memory (used by `Mail.fake()`) |
| `smtp` | Delivers over SMTP |

> [!NOTE]
> SMTP attachment handling is partial. If you rely heavily on attachments, verify the behavior against the `SmtpMailDriver` source for your use case.

<a name="registering-the-provider"></a>
### Registering the Provider

Mail is **opt-in**. Add `MailServiceProvider` to `bootstrap/providers.py`. It binds the `Mail` facade during its boot phase; without it, `Mail` raises a not-bound error.

<a name="generating-mailables"></a>
## Generating Mailables

A mailable is a class that subclasses `Mailable` and implements two methods: `envelope()` and `content()`. Place them under `app/mail/`.

<a name="writing-mailables"></a>
## Writing Mailables

```python
from arvel.mail.mailable import Mailable
from arvel.mail.envelope import Envelope
from arvel.mail.content import Content


class WelcomeMail(Mailable):
    def __init__(self, user_name: str) -> None:
        self.user_name = user_name

    def envelope(self) -> Envelope:
        # No sender set here — it inherits MAIL_FROM_ADDRESS / MAIL_FROM_NAME.
        return Envelope(
            to=["user@example.com"],
            subject="Welcome to Arvel!",
        )

    def content(self) -> Content:
        return Content(html_view="emails/welcome.html", text_view="emails/welcome.txt")
```

> [!NOTE]
> Only `to` and `subject` are required. Leave `from_address`/`from_name` unset and the mailer fills them from `MAIL_FROM_ADDRESS` / `MAIL_FROM_NAME` at render time, matching Laravel's global `from`. Set them on the `Envelope` to override per message.

<a name="configuring-the-envelope"></a>
### Configuring the Envelope

The `Envelope` carries the addressing metadata — subject, recipients, and optionally `from_address`/`from_name`/cc/bcc/reply_to. When you don't set a sender, the configured `MAIL_FROM_ADDRESS` / `MAIL_FROM_NAME` are applied. A `from_name` renders as a display name in the `From` header (`"Arvel App" <hello@example.com>`).

<a name="configuring-the-content"></a>
### Configuring the Content

`Content` carries the body in one of two modes. Inline bodies go in `html=` / `text=` as literal strings. Template bodies go in `html_view=` / `text_view=` as Jinja2 template names, with `data=` holding the shared context. Inline and template forms are mutually exclusive per body, and at least one body must be set:

```python
# Inline body — used verbatim
Content(html="<h1>Hello</h1>")

# Template-rendered body — names resolved by the Jinja2 environment
Content(
    html_view="emails/welcome.html",
    text_view="emails/welcome.txt",
    data={"name": "Ada"},
)
```

> [!NOTE]
> Passing a template path to `html=`/`text=` sends that string literally — template rendering only happens for `html_view=`/`text_view=`. When only an HTML body is given, the mailer auto-derives a plain-text alternative.

<a name="attachments"></a>
### Attachments

Override `attachments()` to return a list of `Attachment` objects. The default is no attachments:

```python
from arvel.mail.attachment import Attachment


class InvoiceMail(Mailable):
    def attachments(self) -> list[Attachment]:
        return [
            Attachment(
                name="2026-01.pdf",
                mime="application/pdf",
                path="invoices/2026-01.pdf",
            )
        ]
```

`Attachment` takes a `name` and `mime`, plus either a `path` (file on disk) or `data` (raw bytes). The SMTP driver reads `path` at send time and sets the part's `Content-Type` from `mime`. Provide one of `path`/`data` — an attachment with neither raises a `MailException`.

<a name="sending-mail"></a>
## Sending Mail

Use the fluent `to(...).send(mailable)` chain. Both steps run through the `Mail` facade, and `send` is a coroutine:

```python
from arvel.facades.mail import Mail

await Mail.to("user@example.com").send(WelcomeMail(user_name="Ada"))
```

<a name="testing"></a>
## Testing

`Mail.fake()` swaps the active driver for an in-memory one. It works both directly and as a context manager (which restores the original driver on exit):

```python
with Mail.fake() as mailbox:
    await Mail.to("user@example.com").send(WelcomeMail(user_name="Ada"))
    assert len(mailbox.sent) == 1
```
