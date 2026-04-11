# Mail

Transactional email is one of those features that looks simple until it is not—templates, attachments, multi-part HTML, and failure modes all pile up. Arvel’s mail stack centers on **`MailContract`** and typed **`Mailable`** objects, with drivers for **SMTP**, **log** (dump to logs in development), and **null** (silence in tests).

You inject the mailer from the container and keep message shape in dataclasses—similar to Laravel mailables, with Pythonic defaults.

## Mailables

Subclass **`Mailable`** and set recipients, subject, body, optional HTML, template name, and context for rendering. Attachments use the **`Attachment`** helper.

```python
from arvel.mail.mailable import Attachment, Mailable


class WelcomeEmail(Mailable):
    subject: str = "Welcome to our app"
    template: str = "mail/welcome.html"

    def __init__(self, to_email: str, name: str) -> None:
        super().__init__()
        self.to = [to_email]
        self.context = {"name": name}


class InvoiceMail(Mailable):
    subject: str = "Your invoice"
    attachments: list[Attachment]  # set in __init__ with bytes + filename
```

Rendering integrates with your template engine where configured; plain `body` / `html_body` work for simple cases.

## Sending mail

Resolve **`MailContract`** and call its send API (exact method names follow the implementation—typically an async `send` accepting a `Mailable`):

```python
from arvel.mail.contracts import MailContract


async def register_user(mailer: MailContract, email: str, name: str) -> None:
    await mailer.send(WelcomeEmail(email, name))
```

## Drivers

- **SMTP** — real delivery through your provider
- **Log** — writes message summaries to logs—perfect when you do not want to spam inboxes during development
- **Null** — no network I/O in automated tests

## Operational tips

Configure retries and timeouts at the SMTP layer, watch bounce and complaint webhooks outside the framework, and **never log full bodies** with live user content in production unless your retention policy says otherwise.

Mail in Arvel is meant to feel approachable: define a mailable, pass it to the contract, let configuration pick the driver. Same comfort as Laravel’s mail layer, with async boundaries that fit Starlette-style apps.
