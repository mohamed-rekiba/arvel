# Notifications

<a name="introduction"></a>
## Introduction

In addition to [mail](mail.md), Arvel supports sending notifications across a variety of channels — log, mail, database, and broadcast. A single notification class describes the message once, then renders itself differently per channel. Notifications are sent to **notifiables** (typically your `User` model via the `Notifiable` mixin).

<a name="quick-start"></a>
### Quick start

```python
# bootstrap/providers.py
from arvel.notifications.providers.notification_service_provider import NotificationServiceProvider

providers = [NotificationServiceProvider, ...]
```

```python
# app/notifications/invoice_paid.py
from typing import Any
from arvel.notifications.notification import Notification


class InvoicePaid(Notification):
    def __init__(self, invoice_id: int) -> None:
        self.invoice_id = invoice_id

    def via(self, notifiable: Any) -> list[str]:
        return ["mail", "database", "log"]

    def to_database(self, notifiable: Any) -> dict[str, Any]:
        return {"invoice_id": self.invoice_id}
```

```python
from arvel.facades.notification import Notification
from arvel.notifications.notifiable import Notifiable


class User(Model, Notifiable):
    ...


await Notification.send(user, InvoicePaid(invoice_id=42))
# or, on a Notifiable model:
await user.notify(InvoicePaid(invoice_id=42))
```

For the `database` channel, publish and run the migration first:

```bash
arvel vendor:publish --tag=arvel-notifications
arvel migrate
```

> [!NOTE]
> The `mail` channel registers only when [Mailer](mail.md) is bound; `database` needs a SQLAlchemy session factory. The `log` and `broadcast` channels are always available.

<a name="registering-the-provider"></a>
## Registering the Provider

Notifications are **opt-in**. Add `NotificationServiceProvider` to `bootstrap/providers.py`. It binds the `Notification` facade and publishes the notifications-table migration. See [Service Providers](../core-concepts/service-providers.md#opt-in-providers).

<a name="generating-notifications"></a>
## Generating Notifications

A notification subclasses `Notification` and implements `via()` to declare its channels, plus one `to_*` method per channel. Place them under `app/notifications/`.

```python
from typing import Any
from arvel.notifications.notification import Notification
from arvel.mail.mailable import Mailable


class InvoicePaid(Notification):
    def __init__(self, invoice_id: int) -> None:
        self.invoice_id = invoice_id

    def via(self, notifiable: Any) -> list[str]:
        return ["mail", "database"]

    def to_mail(self, notifiable: Any) -> Mailable | None:
        return InvoicePaidMail(self.invoice_id)

    def to_database(self, notifiable: Any) -> dict[str, Any]:
        return {"invoice_id": self.invoice_id}
```

`InvoicePaidMail` is one of your own [mailables](mail.md) — `to_mail()` returns it (or `None` to skip the mail channel).

<a name="specifying-delivery-channels"></a>
## Specifying Delivery Channels

`via()` returns the list of channel names to use for a given notifiable. You can branch on the notifiable to choose channels per user:

```python
def via(self, notifiable: Any) -> list[str]:
    return notifiable.notification_channels or ["mail"]
```

> [!WARNING]
> Returning a channel name that isn't registered raises `UnknownChannelError`. Make sure the backing service (Mailer, session factory) is bound before listing `mail` or `database`.

<a name="channel-formatting"></a>
## Channel Formatting

<a name="mail-notifications"></a>
### Mail Notifications

`to_mail()` returns a [Mailable](mail.md) (or `None` to skip). The mail channel delivers it through the bound Mailer.

<a name="database-notifications"></a>
### Database Notifications

`to_database()` returns a dict stored in the notifications table's data column. The default is an empty dict.

<a name="broadcast-notifications"></a>
### Broadcast Notifications

`to_broadcast()` returns a dict pushed through the [broadcast](broadcasting.md) driver. For the broadcast channel the dict must carry `channels` and `data` — e.g. `{"channels": ["users.1"], "data": {"invoice_id": 42}}`. The event name on the wire is the notification class name. A payload missing `channels` is logged and skipped.

<a name="the-notifiable-mixin"></a>
### The Notifiable Mixin

Mix `Notifiable` into any model with an `id` field to get `notify()` and `notify_now()`:

```python
from arvel.notifications.notifiable import Notifiable

class User(Model, Notifiable):
    ...


await user.notify(InvoicePaid(invoice_id=42))       # respects ShouldQueue
await user.notify_now(InvoicePaid(invoice_id=42))   # always inline
```

Both delegate to the bound `NotificationManager` — same behavior as `Notification.send()` / `Notification.send_now()`.

<a name="sending-notifications"></a>
## Sending Notifications

Send through the `Notification` facade. Both methods are coroutines:

```python
from arvel.facades.notification import Notification

await Notification.send(user, InvoicePaid(invoice_id=42))
```

If a single channel fails, the error is logged and the remaining channels still deliver.

<a name="queued-notifications"></a>
## Queued Notifications

Mix in `ShouldQueue` to push delivery onto the [queue](queues.md) instead of sending inline:

```python
from arvel.notifications.notification import Notification
from arvel.notifications.should_queue import ShouldQueue


class InvoicePaid(Notification, ShouldQueue):
    ...
```

`Notification.send()` enqueues queued notifications automatically. Use `Notification.send_now()` to force inline delivery and bypass the queue. If the queue isn't configured, queued notifications fall back to inline delivery.

A queued job carries the notification and notifiable as `module.ClassName` keys, not pickled objects. The worker resolves them from an allowlist built when those classes are imported — it never imports a class path straight from the queue payload. So the worker must import the modules that define your notifications and notifiable models (normal app boot does this). A payload referencing an unknown class is rejected instead of imported. See [Queues](queues.md#running-the-worker).

<a name="testing"></a>
## Testing

`Notification.fake()` records sends without hitting real channels:

```python
from arvel.facades.notification import Notification

with Notification.fake():
    await user.notify(InvoicePaid(invoice_id=42))
    Notification.assert_sent_to(user, InvoicePaid)
    Notification.assert_not_sent_to(user, OrderShipped)
    Notification.assert_nothing_sent()
```
