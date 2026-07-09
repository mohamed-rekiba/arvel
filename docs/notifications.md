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

Notifications are I/O — send them in the background so the request returns immediately. You don't
need to hand-wrap a notification in your own `Job`: make it `ShouldQueue` and `send`/`notify`
enqueues it for you, one job per channel, after the surrounding transaction commits:

```python
from arvel.events import ShouldQueue
from arvel.notifications import Notification

class InvoicePaid(Notification, ShouldQueue):
    def __init__(self, invoice):
        self.invoice = invoice

    def via(self, notifiable):
        return ["mail", "database"]

    def to_mail(self, notifiable):
        return Mailable().subject("Payment received").html(
            f"<p>We received your payment of {self.invoice.total}.</p>"
        )

    def to_array(self, notifiable):
        return {"invoice_id": self.invoice.id}

await user.notify(InvoicePaid(invoice))   # {"queued": True} — mail + database each their own job
```

This is `NotificationManager.send`'s `isinstance(notification, ShouldQueue)` branch — no queue
bound, or the notification isn't `ShouldQueue`, and it just sends inline instead (same call, no
code change either side).

To send later rather than now — a reminder, a follow-up nudge — use `manager.later(delay, ...)`
(`NotificationManager.later`, which schedules through the queue's durable `dispatch_after`) instead
of `send`, regardless of `ShouldQueue`:

```python
await NotificationManager().later(3600, user, PaymentReminder(invoice))  # in an hour
```

### Throttling a queued notification: `middleware()`

A notification can declare its own queued-send middleware — most usefully a rate limit — by
overriding `Notification.middleware()`. It reuses the same job-middleware onion a hand-written `Job`
already gets (`Job.middleware()`, `arvel.queue.middleware`), so `RateLimited`/`WithoutOverlapping`/
`ThrottlesExceptions` all work here too:

```python
from arvel.http.rate_limiter import RateLimiter
from arvel.queue.middleware import RateLimited

class PaymentReminder(Notification, ShouldQueue):
    def __init__(self, invoice):
        self.invoice = invoice
        self.invoice_id = invoice.id   # keep a plain scalar for middleware() — see the note below

    def via(self, notifiable):
        return ["mail"]

    def to_mail(self, notifiable):
        ...

    def middleware(self):
        from arvel.kernel import app

        # resolve the limiter fresh here, don't store it on `self` — the notification is
        # serialized across the queue, and a live limiter can't survive that round trip.
        limiter = RateLimiter(app().make("cache"))
        key = f"reminder:{self.invoice_id}"
        return [RateLimited(limiter, key=key, max_attempts=1, decay_seconds=86400)]
```

Over the limit, the job is released back onto the queue instead of running — not a failure, just
deferred until the window clears.

!!! warning "`middleware()` sees only plain state, not rehydrated attributes"
    `middleware()` runs *before* the job decodes its stored notification, so any attribute is still
    in its serialized form: a Model is a `{id}` reference, not a live row, and a `datetime` is a
    dict. Key the limiter on a plain scalar you captured in `__init__` (`self.invoice_id` above),
    **not** `self.invoice.id` — that works in `to_mail`/`handle` (which run after rehydration) but
    raises here.

**Queued-rail only.** `middleware()` runs in the worker, wrapping the job's `handle()` — an inline
send (not `ShouldQueue`, or no queue bound) has no job at all, so nothing ever consults it. A
rate-limited notification sent inline goes through every time; make it `ShouldQueue` (or send it via
`later`) if the limit needs to actually bite.

## Common mistakes & gotchas

- **A channel in `via` with no content method.** If `via` returns `"mail"`, implement
  `to_mail`; `"apprise"` needs `apprise_urls`. A listed channel with no matching method has
  nothing to send.
- **Hard-coding the channel list.** `via(notifiable)` receives the recipient — use it to choose
  channels per user (e.g. SMS only if they opted in), not a fixed list.
- **Forgetting the `[notifications]` extra.** The `apprise` channel needs Apprise installed;
  without it, fall back to `mail`.

## How it works

`NotificationManager.send` checks the notification first: `isinstance(notification, ShouldQueue)`
with a queue bound enqueues one `SendQueuedNotification` job per `via(notifiable)` channel (each
riding the after-commit seam) and returns `{"queued": True}` immediately; otherwise it falls through
to `send_now`. `later(delay, notifiable, notification)` always queues, via the same per-channel job,
but through the queue's durable `dispatch_after` instead of an immediate enqueue.

`send_now` asks the notification's `via(notifiable)` for the channel list, checks
`should_send(notifiable, channel)` for each (skipping silently on `False`), then dispatches the
rest: `mail` renders `to_mail()` and hands it to the mail manager; `database` persists a
`DatabaseNotification` row keyed to the notifiable (or, with no database bound, returns the
`to_array()` payload); `broadcast` sends a `BroadcastNotification` event through the Broadcast
manager; `apprise` feeds `apprise_urls()` into an Apprise instance (lazily imported) that fans the
message out to every configured service. Each channel reports its result, keyed by channel — a
skipped channel has no entry at all.

A queued `SendQueuedNotification` job also surfaces the notification's `middleware()` into the
worker's job-middleware onion (`Job.middleware()`) before running `send_now` for its one channel —
covered above under [Throttling a queued notification](#throttling-a-queued-notification-middleware).

## See also

- [Mail](mail.md) — the `mail` channel's transport.
- [Queues & Jobs](queues.md) — sending notifications in the background.
