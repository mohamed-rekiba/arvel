# Events

Arvel events provide a simple observer pattern, allowing you to subscribe and listen for events that occur in your application. Events typically represent things that have already happened — "a user signed up", "an order was paid", "a comment was posted" — and listeners react to them.

Events are perfect for decoupling. Your `OrderService` doesn't need to know that sending a receipt email is a side effect of completing an order. It dispatches an `OrderCompleted` event, and a listener takes care of the email.

## Defining events

An event is a Pydantic model:

```python
from pydantic import BaseModel
from datetime import datetime


class OrderCompleted(BaseModel):
    order_id: int
    customer_email: str
    total_cents: int
    completed_at: datetime
```

Pydantic gives you validation and JSON-serialization for free, which matters for queued events (more below).

## Defining listeners

A listener is a function or class. The async function form:

```python
async def send_order_receipt(event: OrderCompleted) -> None:
    await Mail.to(event.customer_email).send(OrderReceiptMail(event.order_id))
```

The class form, useful when you have shared state or dependencies:

```python
from arvel.events import Listener


class SendOrderReceipt(Listener[OrderCompleted]):
    def __init__(self, mailer: Mailer) -> None:
        self._mailer = mailer

    async def handle(self, event: OrderCompleted) -> None:
        await self._mailer.send(OrderReceiptMail(event.order_id))
```

Class listeners are resolved through the container, so constructor dependencies are injected.

## Registering listeners

Register in a service provider:

```python
from arvel.facades import Event


class EventServiceProvider(ServiceProvider):
    async def boot(self) -> None:
        Event.listen(OrderCompleted, send_order_receipt)
        Event.listen(OrderCompleted, SendOrderReceipt)
        Event.listen(OrderCompleted, UpdateInventory)
```

Multiple listeners for the same event run in registration order. By default they run **sequentially** within the request lifecycle.

## Dispatching

```python
from arvel.facades import Event


await Event.dispatch(
    OrderCompleted(
        order_id=order.id,
        customer_email=order.customer.email,
        total_cents=order.total_cents,
        completed_at=now(),
    ),
)
```

## Queued listeners (run in background)

For listeners that should not block the request — sending email, calling external APIs, generating reports — mark the listener as `ShouldQueue`:

```python
from arvel.queue import ShouldQueue
from arvel.events import Listener


class SendOrderReceipt(Listener[OrderCompleted], ShouldQueue):
    queue = "emails"

    async def handle(self, event: OrderCompleted) -> None:
        await Mail.to(event.customer_email).send(OrderReceiptMail(event.order_id))
```

When the event fires, Arvel serializes both event and listener and dispatches them to the queue. A worker picks them up and runs the listener.

This is the same pattern as a regular [Job](queues.md) — `ShouldQueue` just bridges events and the job bus.

## Wildcard listeners

For cross-cutting concerns (audit logging, debugging), subscribe to all events:

```python
async def log_every_event(event_name: str, event) -> None:
    Log.info("event.dispatched", event=event_name, payload=event.model_dump())


Event.listen("*", log_every_event)
```

## Event broadcasting

If your event subclasses `ShouldBroadcast`, it also goes out over your broadcasting channel:

```python
from arvel.broadcasting import ShouldBroadcast


class OrderCompleted(BaseModel, ShouldBroadcast):
    order_id: int
    ...

    def channels(self) -> list[str]:
        return [f"orders.{self.order_id}"]
```

See [Broadcasting](broadcasting.md) for details.

## Testing

Swap the dispatcher for an in-memory recorder:

```python
async def test_order_dispatches_completed_event(client) -> None:
    Event.fake()
    await client.post("/orders", json={...})
    Event.assert_dispatched(OrderCompleted, lambda e: e.total_cents == 2500)
```

The fake recorder captures the dispatch intent; listeners don't run. To run a specific listener even under `fake()`, use `Event.fake_except([...])`.

## Where to next?

- [Queues](queues.md) — how `ShouldQueue` listeners run in the background.
- [Broadcasting](broadcasting.md) — when events go out over WebSockets.
- [Notifications](notifications.md) — for user-facing event reactions.
