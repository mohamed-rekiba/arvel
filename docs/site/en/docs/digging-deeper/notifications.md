# Notifications

Sometimes email alone is not enough—you want an in-app feed, a database row for auditing, or a future Slack hook without rewriting the feature. Arvel’s **`NotificationContract`** and **`Notification`** base class follow the Laravel pattern: one object describes **how** to reach a user across **channels**, and the dispatcher routes it.

At **v0.1.0**, channels include **mail** (built on `MailContract`) and **database** (structured payloads you persist with your own models), with room to extend toward Slack-style payloads in userland.

## Defining a notification

Subclass **`Notification`** and implement:

- **`via(notifiable)`** — return a list of channel names (`"mail"`, `"database"`, etc.)
- **`to_mail(notifiable)`** — return a **`MailMessage`** for the mail channel
- **`to_database(notifiable)`** — return a **`DatabasePayload`** for the database channel

```python
from arvel.notifications.notification import DatabasePayload, MailMessage, Notification


class InvoicePaidNotification(Notification):
    def __init__(self, invoice_id: int) -> None:
        self.invoice_id = invoice_id

    def via(self) -> list[str]:
        return ["mail", "database"]

    def to_mail(self, notifiable: object) -> MailMessage:
        return MailMessage(
            subject="Invoice paid",
            body=f"Invoice #{self.invoice_id} was paid.",
        )

    def to_database(self, notifiable: object) -> DatabasePayload:
        return DatabasePayload(
            type="invoice_paid",
            data={"invoice_id": self.invoice_id},
        )
```

## Queued notifications

Inherit **`ShouldQueue`** alongside **`Notification`** when you want dispatch to go through the queue so HTTP handlers return quickly—mirroring Laravel’s `ShouldQueue` interface.

```python
from arvel.notifications.notification import Notification, ShouldQueue


class HeavyDigest(ShouldQueue, Notification): ...
```

## Dispatching

Use **`NotificationDispatcher`** (the `NotificationContract` implementation) from the container: it fans out to registered channels based on `via()`. Your **notifiable** object is typically a user model or a small protocol-implementing type that supplies addresses and IDs.

## When to use notifications vs mail only

Reach for **`Mailable`** when the message is **just email**. Reach for **`Notification`** when the **same event** might surface in the UI, email, and audit tables—one class, multiple channels, less duplication.

That is the Laravel-shaped ergonomics Arvel aims for: expressive classes, channel methods, and a contract that keeps tests swappable with fakes.
