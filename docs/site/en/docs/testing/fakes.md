# Fakes

Sometimes you want to prove *your* code’s behavior without sending real email, touching Redis, or uploading to S3. Laravel gives you fakes for the mailer, queue, and more; Arvel ships the same idea for its async contracts—**in-memory doubles** you bind into the container for the duration of a test, plus **assertion helpers** that answer “did we dispatch the right job?” or “was this key written to cache?”.

All of these are re-exported from **`arvel.testing`** so a single import line keeps tests tidy:

```python
from arvel.testing import (
    BroadcastFake,
    CacheFake,
    EventFake,
    LockFake,
    MailFake,
    MediaFake,
    NotificationFake,
    QueueFake,
    StorageFake,
)
```

Swap the real driver for the fake when you compose your app or test fixtures, exercise the code under test, then call the **`assert_*`** methods on the fake. Warm narrative aside, the rule is simple: **if the production code only talks to the contract, the fake is a faithful stand-in.**

## CacheFake

**`CacheFake`** extends the in-memory cache driver and records every **`put`** key so you can assert cache warming, cache busting, or “must not write secrets to cache” behavior.

```python
from arvel.testing import CacheFake

async def test_warms_profile_cache(cache: CacheFake):
    await run_action_that_should_cache()

    cache.assert_put("user:42:profile")
```

**`assert_not_put`**, **`assert_nothing_put`**, and the base cache API cover the negative cases.

## MailFake

**`MailFake`** implements the mail contract and stores every **`Mailable`** passed to **`send`**. Assertions line up with how you think about outbound mail:

```python
from arvel.testing import MailFake

def test_sends_welcome_email(mail: MailFake):
    # ... trigger code that sends mail ...

    mail.assert_sent_to("newuser@example.com")
    mail.assert_sent_count(1)


def test_does_not_mail_on_validation_error(mail: MailFake):
    # ... trigger code that should skip sending ...

    mail.assert_nothing_sent()
```

**`assert_sent`** matches keyword arguments against attributes on captured mailables (all string values), and **`assert_not_sent`** fails if a matching mailable was sent when it should not have been.

## QueueFake

**`QueueFake`** captures **`Job`** instances from **`dispatch`**, **`later`**, and **`bulk`**. Use it to verify background work is scheduled with the right type and payload—without a worker process.

```python
from arvel.testing import QueueFake

from myapp.jobs import SendReminder


def test_dispatches_reminder_job(queue: QueueFake):
    # ... trigger dispatch ...

    queue.assert_pushed(SendReminder)
    queue.assert_pushed_with(SendReminder, user_id=99)
    queue.assert_pushed_on("notifications", SendReminder)
    queue.assert_nothing_pushed()
```

**`pushed_count`** and **`assert_pushed_count`** let you tighten tests when duplicate dispatches would be a bug.

## StorageFake

**`StorageFake`** keeps bytes in a dictionary and implements the storage contract—**`put`**, **`get`**, **`exists`**, **`delete`**, **`list`**, URLs, and sizes. Assertions focus on paths:

```python
from arvel.testing import StorageFake

async def test_stores_avatar(storage: StorageFake):
    # ... code that stores "avatars/1.png" ...

    storage.assert_stored("avatars/1.png")
    storage.assert_not_stored("avatars/2.png")
    storage.assert_nothing_stored()
```

## LockFake

**`LockFake`** extends the in-memory lock driver and records keys successfully acquired—ideal for asserting deduplication or “this critical section ran under lock”:

```python
from arvel.testing import LockFake

async def test_acquires_invoice_lock(lock: LockFake):
    # ... code that locks invoice:123 ...

    lock.assert_acquired("invoice:123")
    lock.assert_nothing_acquired()
```

## MediaFake

**`MediaFake`** implements the media library contract in memory, including collections, validation, and events. For tests that only care that media was attached, use helpers like **`assert_added`**, **`assert_added_count`**, and **`assert_nothing_added`** (with optional collection name).

## NotificationFake

**`NotificationFake`** records **`(notifiable, notification)`** pairs from **`send`**. Typical assertions:

```python
from arvel.testing import NotificationFake

def test_notifies_owner(notifications: NotificationFake):
    # ... trigger notification ...

    notifications.assert_sent_to(user_instance)
    notifications.assert_sent_type(PostPublishedNotification)
    notifications.assert_nothing_sent()
```

## EventFake

**`EventFake`** captures dispatched domain events so listeners do not run—perfect for isolating “was **`OrderShipped`** fired?” without side effects:

```python
from arvel.testing import EventFake

from myapp.events import OrderShipped


def test_dispatches_shipped_event(events: EventFake):
    # ... action ...

    events.assert_dispatched(OrderShipped)
    events.assert_dispatched(OrderShipped, predicate=lambda e: e.order_id == 5)
    events.assert_not_dispatched(OrderCancelled)
    events.assert_nothing_dispatched()
```

**`dispatched_count`** and **`assert_dispatched_count`** mirror the queue fake’s ergonomics.

## BroadcastFake

**`BroadcastFake`** records channel names, event names, and payloads from **`broadcast`**. Use it when you want confidence that websockets or Pusher-style channels received the right message:

```python
from arvel.testing import BroadcastFake

def test_broadcasts_status_changed(broadcast: BroadcastFake):
    # ... action ...

    broadcast.assert_broadcast("status.changed", channel="orders.99")
    broadcast.assert_broadcast_on("orders.99")
    broadcast.assert_nothing_broadcast()
```

## Wiring fakes in practice

How you inject a fake depends on your app’s container: bind **`MailContract`** to **`MailFake()`** for the test module, or provide a fixture that yields the fake and resets it between tests. The important part is consistency—production code should depend on **`MailContract`**, not a concrete SMTP class, so the swap is one line.

Assert interactions after the act: **dispatch the job, send the mail, then ask the fake**. That keeps tests fast, deterministic, and honest about what you are proving—exactly the workflow Laravel developers expect, adapted for Arvel’s async, contract-first world.
