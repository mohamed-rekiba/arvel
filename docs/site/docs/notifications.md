# Notifications

Notifications are the multi-channel sibling of [Mail](mail.md). Whereas a Mailable always lands in an inbox, a Notification can go to mail, database, broadcast (WebSocket), Slack, SMS, or any custom channel — from a single class.

## Defining a Notification

```python
from arvel.notifications import Notification
from arvel.mail import MailMessage


class OrderShipped(Notification):
    def __init__(self, order_id: int, tracking_url: str) -> None:
        self.order_id = order_id
        self.tracking_url = tracking_url

    def channels(self, notifiable) -> list[str]:
        return ["mail", "database", "broadcast"]

    def to_mail(self, notifiable) -> MailMessage:
        return (
            MailMessage()
            .subject(f"Order #{self.order_id} has shipped!")
            .line(f"Track your shipment: {self.tracking_url}")
        )

    def to_database(self, notifiable) -> dict:
        return {
            "order_id": self.order_id,
            "tracking_url": self.tracking_url,
        }

    def to_broadcast(self, notifiable) -> dict:
        return {"order_id": self.order_id, "status": "shipped"}
```

`channels(notifiable)` returns the list of channels this notification should fire on for **this particular recipient**. You can branch on user preferences — some users want SMS, others only want email.

## Sending

```python
from arvel.facades import Notification as N


await N.send(user, OrderShipped(order_id=42, tracking_url="..."))

# Multiple recipients
await N.send([alice, bob], OrderShipped(order_id=42, tracking_url="..."))

# On-demand (no User model — just an address)
await N.route("mail", "alice@example.com").notify(OrderShipped(...))
```

## The "notifiable" trait

For your `User` model (or any other class) to receive notifications, mix in `Notifiable`:

```python
from arvel.notifications import Notifiable


class User(Model, Notifiable):
    ...
```

This gives the model:

```python
await user.notify(OrderShipped(...))
await user.notify_now(OrderShipped(...))   # synchronous, skip queue
```

By default, notifications are **queued**. Use `notify_now(...)` only for tests or where blocking is acceptable.

## The database channel

For in-app notifications (bell icon UI), use the `database` channel. Generate a migration and define the schema:

```bash
uv run arvel make:migration create_notifications_table
```

```python
# database/migrations/<timestamp>_create_notifications_table.py
from arvel.database import Blueprint, Schema


async def up(schema: Schema) -> None:
    def build(t: Blueprint) -> None:
        t.uuid("id").primary()
        t.string("type")
        t.string("notifiable_type")
        t.big_integer("notifiable_id")
        t.json("data")
        t.timestamp("read_at").nullable()
        t.timestamps()
        t.index(["notifiable_type", "notifiable_id"])

    Schema.create("notifications", build)


async def down(schema: Schema) -> None:
    Schema.drop("notifications")
```

```bash
uv run arvel migrate
```

Access notifications via the relationship on a notifiable model:

```python
unread = await user.unread_notifications.get()
all_notifications = await user.notifications.paginate(page=1, per_page=20)

# Mark one as read
notification = await user.notifications.find(notification_id)
await notification.mark_as_read()

# Mark all as read
await user.unread_notifications.update(read_at=now())
```

## The broadcast channel

When a notification fires on `broadcast`, Arvel sends it to the configured broadcasting driver on a per-user private channel:

```
private-App.Models.User.{userId}
```

The frontend subscribes to this channel via [Laravel Echo](broadcasting.md#client-side-subscription) and pops a toast when a notification arrives.

## Custom channels

Build your own channel by implementing the `Channel` protocol:

```python
from arvel.notifications import Channel


class TwilioSmsChannel(Channel):
    def __init__(self, client: TwilioClient) -> None:
        self._client = client

    async def send(self, notifiable, notification) -> None:
        message = notification.to_sms(notifiable)
        await self._client.messages.create(
            to=notifiable.phone_number,
            from_=self._client.from_number,
            body=message,
        )
```

Register it in a service provider:

```python
class NotificationServiceProvider(ServiceProvider):
    async def boot(self) -> None:
        N.extend("sms", lambda: TwilioSmsChannel(TwilioClient.from_env()))
```

Then notifications that include `"sms"` in `channels(...)` and define `to_sms(...)` will fan out through it.

## Testing

For mail notifications, swap the mail driver and inspect sent messages:

```python
async def test_shipping_notification(client) -> None:
    driver = Mail.fake()
    await ship_order(order_id=42)
    assert len(driver.sent) == 1
    assert driver.sent[0].to == user.email
```

For non-mail channels (SMS, Slack, etc.) use `unittest.mock.patch` on the channel's send method, or inject a spy channel in the service provider before the test runs.

## Where to next?

- [Mail](mail.md) — for email-only notifications.
- [Broadcasting](broadcasting.md) — channel + auth for real-time delivery.
- [Queues](queues.md) — every notification is a queued job by default.
