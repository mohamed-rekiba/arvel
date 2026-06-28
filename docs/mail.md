# Mail

Sending email touches a lot of fiddly concerns at once — building a MIME message, rendering an HTML
body, attaching files, talking to an SMTP server, and not blocking the request while you do it. arvel
wraps all of that behind an async **Mailable** (the message) and a driver-based manager (how it's
delivered): in development a `log` driver records messages without touching the network; in
production an `smtp` driver sends for real. Your code is identical either way — only config changes.

This page covers writing a Mailable, sending it, the drivers, queueing mail, and testing it without
sending anything.

!!! note "Needs the `[mail]` extra"
    `uv add 'arvel[mail]'` (aiosmtplib for SMTP, plus markdown rendering). The `log` driver works
    without a server, so it's ideal for development and tests.

## A Mailable

A Mailable is your message class. Override `build()` and set the subject and HTML body with the
fluent setters:

```python
from arvel.mail import Mailable

class WelcomeMail(Mailable):
    def __init__(self, user):
        super().__init__()
        self.user = user

    def build(self):
        return self.subject("Welcome to Acme").html(
            f"<h1>Hi {self.user.name}</h1><p>Glad you're here.</p>"
        )
```

`subject()` and `html()` return `self`, so they chain. `build()` is called for you when the
message is rendered — you never call it directly.

You can also write the body in **Markdown** (rendered to HTML) — needs the `[mail]` extra:

```python
def build(self):
    return self.subject("Welcome").markdown("# Hi\n\nThanks for **joining** Acme.")
```

You can also attach files: `.attach("invoices/2026.pdf")` or `.attach_data(png_bytes, "logo.png")`.

## Sending

Open a pending send with the recipients, then `send` the Mailable:

```python
from arvel import Mail

await Mail.to(user).send(WelcomeMail(user))
await Mail.to("ops@acme.test").send(AlertMail(incident))
```

`to()` accepts a user object (its `email` attribute is used) or a raw address string, and
multiple recipients:

```python
await Mail.to(alice, bob, "carbon-copy@acme.test").send(DigestMail())
```

Add `cc` / `bcc` recipients by chaining (Laravel `->cc`/`->bcc`); `bcc` recipients aren't shown to
the others:

```python
await Mail.to(user).cc(manager).bcc("audit@acme.test").send(InvoiceMail(order))
```

Set the **sender** on the Mailable with `from_` (named with a trailing underscore — `from` is a
Python keyword) and `reply_to`:

```python
class WelcomeMail(Mailable):
    def build(self):
        return (self.subject("Welcome")
                    .from_("noreply@acme.test")
                    .reply_to("support@acme.test")
                    .markdown("# Hi"))
```

## Drivers

The active driver comes from `mail.default` in config:

| Driver | Behaviour | Needs |
|--------|-----------|-------|
| `log` (default) | records each message in memory; sends nothing | nothing |
| `smtp` | sends via a real `aiosmtplib.SMTP` connection | `mail.smtp` host/port config |

```python
# config/mail.py
MAIL = {
    "default": "smtp",
    "smtp": {"host": "smtp.acme.test", "port": 587},
}
```

## Worked example: a controller action

```python
async def register(request):
    user = await User.create(**request.validated())
    await Mail.to(user).send(WelcomeMail(user))   # log in dev, real SMTP in prod
    return {"status": "registered"}
```

## Variations

### Queue the send
Email is slow — push it to the background so the request returns immediately. Dispatch a job
that sends the mail (see [Queues & Jobs](queues.md)):

```python
class SendWelcome(Job):
    def __init__(self, user): self.user = user        # serialized as (User, pk)
    async def handle(self):
        await Mail.to(self.user).send(WelcomeMail(self.user))

await SendWelcome.dispatch(user)
```

Or let the mailable queue itself: make it a `ShouldQueue` and `Mail.to(...).send(...)` enqueues it
automatically (when a queue is bound) instead of sending inline. The mailable is serialized as its
class + attribute state (model attributes become `(class, pk)` refs, re-fetched in the worker), so it
travels safely across a real broker (redis); `build()` runs in the worker. Keep a queued mailable's
attributes simple/serializable (ids, strings, models). **Add attachments inside `build()`** (which
runs in the worker), not before dispatch — raw bytes set on the instance don't round-trip through the
broker's JSON cleanly.

## Common mistakes & gotchas

- **Forgetting `super().__init__()`** in a Mailable's `__init__` — the subject/body buffers
  live on the base, so skipping it raises an `AttributeError` when you set them.
- **Calling `build()` yourself.** Rendering calls it; calling it twice just rebuilds. Put your
  content in `build()`, not in `__init__`.
- **Expecting `log` to send.** In dev nothing leaves the process — that's the point. Switch
  `mail.default` to `smtp` (and configure a host) to actually send.
- **A bare string with no `@`.** `to("ops")` is treated as the literal address; pass a real
  email or a user with an `email` attribute.

## Testing

Swap a recording fake and assert what was sent — no SMTP, no log inspection:

```python
from arvel.testing import fake
from arvel import Mail

mail = fake(Mail)
await register(request)
mail.assert_sent(WelcomeMail)
```

## How it works

`Mail` is a facade over a `MailManager` (a driver manager). `to()` returns a `PendingMail`
holding the recipients; `send()` renders the Mailable to a stdlib `EmailMessage` (subject +
HTML body), stamps the `To` header, and hands it to the active transport. The `log` transport
appends to an in-memory list; the `smtp` transport opens an `aiosmtplib.SMTP` connection and
sends. aiosmtplib is imported lazily, so `import arvel` stays light until you actually send.

## See also

- [Queues & Jobs](queues.md) — sending mail in the background.
- [Events](events.md) · [Validation](validation.md)
