# Mail

Arvel sends email through the `Mail` facade with the same Mailable + driver pattern as Laravel. Compose an email as a class, configure a driver, and `Mail.to(...).send(...)` does the rest.

## Configuration

```env
MAIL_DRIVER=smtp
MAIL_FROM_ADDRESS=hello@example.com
MAIL_FROM_NAME="Example App"

MAIL_SMTP_HOST=smtp.example.com
MAIL_SMTP_PORT=587
MAIL_SMTP_USERNAME=...
MAIL_SMTP_PASSWORD=...
MAIL_SMTP_ENCRYPTION=tls
```

Available drivers:

| Driver | Use when |
|---|---|
| `smtp` | Generic SMTP server |
| `ses` | AWS SES |
| `mailgun` | Mailgun API |
| `postmark` | Postmark API |
| `log` | Local dev — writes to logs instead of sending |
| `array` | Tests — records sent messages |
| `null` | CI — discards |

## Defining a Mailable

```python
from arvel.mail import Mailable


class WelcomeEmail(Mailable):
    def __init__(self, user_name: str) -> None:
        self.user_name = user_name

    def build(self) -> "WelcomeEmail":
        return (
            self
            .subject(f"Welcome, {self.user_name}!")
            .view("emails.welcome", {"name": self.user_name})
            .preview("Glad to have you on board.")
        )
```

The fluent `build()` method chains the subject, the body template, and any additional metadata.

## Sending

```python
from arvel.facades import Mail


await Mail.to("alice@example.com").send(WelcomeEmail("Alice"))

# Multiple recipients
await Mail.to(["alice@example.com", "bob@example.com"]).send(NewsletterEmail())

# CC / BCC
await (
    Mail
    .to("alice@example.com")
    .cc("manager@example.com")
    .bcc("audit@example.com")
    .send(InvoiceEmail(invoice_id=42))
)
```

## Templates

Mailables render via Jinja2 templates under `resources/views/emails/`:

```
resources/views/emails/welcome.html
```

```html
<!DOCTYPE html>
<html>
<body>
  <h1>Welcome, {{ name }}!</h1>
  <p>Thanks for signing up.</p>
  <p>
    <a href="{{ url('dashboard') }}">Go to your dashboard</a>
  </p>
</body>
</html>
```

For plain-text emails, point at a `.txt` template instead of `.html`:

```python
.view("emails.welcome", template_kind="text")
```

To include both an HTML and a plain-text body, call `.view(...)` twice with different kinds.

## Attachments

```python
class InvoiceEmail(Mailable):
    def __init__(self, invoice_id: int) -> None:
        self.invoice_id = invoice_id

    async def build(self) -> "InvoiceEmail":
        pdf = await Storage.disk("local").get(f"invoices/{self.invoice_id}.pdf")
        return (
            self
            .subject(f"Invoice #{self.invoice_id}")
            .view("emails.invoice", {"invoice_id": self.invoice_id})
            .attach_data(pdf, name=f"invoice-{self.invoice_id}.pdf", mime="application/pdf")
        )
```

`.attach(...)` accepts a filesystem path; `.attach_data(...)` accepts raw bytes.

## Queuing emails

Block as little of the request lifecycle as possible. Mark a Mailable to queue:

```python
from arvel.queue import ShouldQueue


class WelcomeEmail(Mailable, ShouldQueue):
    queue = "emails"
    ...
```

Now `Mail.to(...).send(WelcomeEmail(...))` dispatches a job to the queue instead of blocking. A worker picks it up and actually sends the email.

For one-off scheduled sends:

```python
await Mail.to(...).later(seconds=300).send(ReminderEmail())
```

## Testing

```python
async def test_signup_sends_welcome_email(client) -> None:
    driver = Mail.fake()
    await client.post("/signup", json={"name": "Alice", "email": "a@b.com"})
    assert len(driver.sent) == 1
    assert driver.sent[0].to == "a@b.com"
```

`Mail.fake()` swaps the active driver to an in-memory recorder and returns a context object. Check `driver.sent` (a list of `RenderedMail`) to assert what was sent. No actual SMTP traffic happens while the fake is active.

## Where to next?

- [Notifications](notifications.md) — when you need other channels alongside email.
- [Queues](queues.md) — how `ShouldQueue` works.
- [File Storage](filesystem.md) — for email attachments.
