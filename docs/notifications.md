# Notifications

"Tell the user their order shipped" sounds simple until you realize *how* depends on the user —
email for one, Slack for the team, an in-app row for another. Notifications solve that: you write
the message **once** and declare which **channels** carry it per recipient — email, a database row,
or any of the 80+ services [Apprise](https://github.com/caronc/apprise) supports (Slack, Discord,
Telegram, SMS, push, …).

This page covers writing a notification, sending it, the available channels, and queueing delivery.

!!! note "Needs an extra per channel"
    The `database` channel is **core** (needs a configured database). The `mail` channel needs
    `uv add 'arvel[mail]'`; the `apprise` channel (Slack/Discord/Telegram/SMS/push) needs
    `uv add 'arvel[notifications]'`.

## A notification

Subclass `Notification`, list the channels in `via`, and provide the content for each channel
you use:

```python
from arvel.notifications import Notification
from arvel.mail import Mailable

class InvoicePaid(Notification):
    def __init__(self, invoice):
        self.invoice = invoice

    def via(self, notifiable):
        return ["mail", "apprise"]                 # which channels for this recipient

    def to_mail(self, notifiable):
        return Mailable().subject("Payment received").html(
            f"<p>We received your payment of {self.invoice.total}.</p>"
        )

    def apprise_urls(self, notifiable):
        return [notifiable.slack_webhook]          # any Apprise URL(s)
```

## Sending

Send to a recipient with the manager, or call `notify` on a notifiable:

```python
from arvel.notifications import NotificationManager

await NotificationManager().send(user, InvoicePaid(invoice))
```

```python
from arvel.notifications import Notifiable

class User(Model, Notifiable):
    ...

await user.notify(InvoicePaid(invoice))            # routes to the user's channels
```

`send` returns a per-channel result dict, so you can see what went where.

### On-demand (no stored model)

To notify an ad-hoc recipient that isn't a model — a raw email, a Slack webhook — use
`AnonymousNotifiable` and set a route per channel:

```python
from arvel.notifications import AnonymousNotifiable

await (AnonymousNotifiable()
       .route("mail", "ops@acme.test")
       .route("slack", "json://hooks.slack.test/...")
       .notify(AlertRaised(incident)))
```

Each `route(channel, route)` tells that channel where to deliver; the manager reads it via
`route_notification_for(channel)` — `mail` takes an address,
apprise channels take a URL (or list of URLs).

## Channels

| Channel | What it does |
|---------|--------------|
| `mail` | renders `to_mail()` and sends it through the [Mail](mail.md) manager |
| `apprise` | pushes to every URL from `apprise_urls()` — Slack, Discord, Telegram, SMS, push, … |
| `database` | persists `to_array()` as a row in the `notifications` table (see below) |
| `broadcast` | sends `to_broadcast()`'s payload through the Broadcast manager, on the notifiable's channel |

A recipient's channels come from the notification's `via()` — different users can receive the
same notification on different channels.

### The `broadcast` channel

```python
class OrderShipped(Notification):
    def via(self, notifiable):
        return ["broadcast", "database"]

    def to_broadcast(self, notifiable):
        return {"order_id": self.order.id}   # defaults to to_array() if you skip this
```

Delivery is a `BroadcastNotification` event on the notifiable's channel — by default
`PrivateChannel(f"{type(notifiable).__name__}.{notifiable.id}")`; override
`receives_broadcast_notifications_on()` on the notifiable to pick a different channel.

### Skipping a channel per send: `should_send`

Override `should_send(notifiable, channel)` to silently skip one channel for a given send (no
error, no result entry) while the rest of `via()` still runs — e.g. a muted digest:

```python
class WeeklyDigest(Notification):
    def should_send(self, notifiable, channel):
        return not (channel == "broadcast" and notifiable.digest_muted)
```

## Stored (database) notifications

The `database` channel writes a row to the `notifications` table — a stored, in-app feed (the "🔔
bell" pattern). The scaffold ships the migration; the row keys off the notifiable (its class +
primary key) and stores `to_array()` as JSON:

```python
class OrderShipped(Notification):
    def via(self, notifiable):
        return ["database"]
    def to_array(self, notifiable):
        return {"order_id": 42, "message": "Your order shipped"}

await user.notify(OrderShipped())
```

A `Notifiable` model reads and updates its stored notifications:

```python
await user.notifications()              # all, newest first
await user.unread_notifications()       # only those with read_at == null

note = (await user.notifications())[0]
note.unread                            # True until read
await note.mark_as_read()              # stamps read_at (idempotent); mark_as_unread() clears it
await user.mark_all_notifications_as_read()
```

Each row is a `DatabaseNotification` (`arvel.notifications.DatabaseNotification`) with a UUID `id`,
`type`, `notifiable_type`/`notifiable_id`, the JSON `data`, and a nullable `read_at`. Without a bound
database the channel returns the `to_array()` payload instead of persisting, so on-demand /
test sends don't error.

## Worked example: queue it

Notifications are I/O — send them in the background so the request returns immediately:

```python
class SendInvoicePaid(Job):
    def __init__(self, user, invoice):
        self.user = user
        self.invoice = invoice
    async def handle(self):
        await self.user.notify(InvoicePaid(self.invoice))

await SendInvoicePaid.dispatch(user, invoice)
```

## Common mistakes & gotchas

- **A channel in `via` with no content method.** If `via` returns `"mail"`, implement
  `to_mail`; `"apprise"` needs `apprise_urls`. A listed channel with no matching method has
  nothing to send.
- **Hard-coding the channel list.** `via(notifiable)` receives the recipient — use it to choose
  channels per user (e.g. SMS only if they opted in), not a fixed list.
- **Forgetting the `[notifications]` extra.** The `apprise` channel needs Apprise installed;
  without it, fall back to `mail`.

## How it works

`NotificationManager.send` asks the notification's `via(notifiable)` for the channel list, checks
`should_send(notifiable, channel)` for each (skipping silently on `False`), then dispatches the
rest: `mail` renders `to_mail()` and hands it to the mail manager; `database` persists a
`DatabaseNotification` row keyed to the notifiable (or, with no database bound, returns the
`to_array()` payload); `broadcast` sends a `BroadcastNotification` event through the Broadcast
manager; `apprise` feeds `apprise_urls()` into an Apprise instance (lazily imported) that fans the
message out to every configured service. Each channel reports its result, keyed by channel — a
skipped channel has no entry at all.

## See also

- [Mail](mail.md) — the `mail` channel's transport.
- [Queues & Jobs](queues.md) — sending notifications in the background.
