# Events

Domain events are the glue between “something happened” and “everything that should react.” Arvel’s event layer will feel familiar if you have used Laravel’s dispatcher: you define **`Event`** subclasses, register **`Listener`** classes, and let the **`EventDispatcher`** fan out work—synchronously by default, or **queued** when you want the request to stay fast.

At **v0.1.0**, events are immutable **Pydantic** models, which keeps payloads structured and serialization-friendly if a listener runs later on the queue.

## Events

Subclass **`Event`** and add fields for your payload. A timestamp is included for you via `occurred_at`.

```python
from arvel.events.event import Event


class OrderShipped(Event):
    order_id: int
    tracking_number: str
```

Keep sensitive fields out of serialized forms when you push work to the queue—use `Field(exclude=True)` on Pydantic fields when needed.

## Listeners

Subclass **`Listener`** and implement **`handle(self, event: YourEvent)`**. The type hint tells the dispatcher which event type you handle.

```python
from arvel.events.listener import Listener


class SendShipmentNotification(Listener):
    async def handle(self, event: OrderShipped) -> None:
        # Send email, broadcast, update projections, etc.
        ...
```

## Queued listeners

Decorate the listener class with **`@queued`** so the framework dispatches it via the queue instead of inline. That mirrors Laravel’s queued listeners: the HTTP worker stays quick, and **`EventDispatcher`** coordinates the handoff (integration points depend on your queue driver).

```python
from arvel.events.listener import Listener, queued


@queued
class IndexOrderInSearch(Listener):
    async def handle(self, event: OrderShipped) -> None: ...
```

Listeners expose **`__queued__`**; the decorator simply sets that flag for you.

## Dispatching

Use **`EventDispatcher`** from your services or hooks after meaningful state changes:

```python
from arvel.events.dispatcher import EventDispatcher


async def ship_order(dispatcher: EventDispatcher, order_id: int) -> None:
    # ... persist shipping ...
    await dispatcher.dispatch(OrderShipped(order_id=order_id, tracking_number="1Z999"))
```

## When to reach for events

Use events when **multiple subsystems** should react to one fact without the core use case knowing every subscriber. Keep listeners small, idempotent where possible, and let the queue absorb spikes when you mark them with **`@queued`**.

That keeps your domain expressive and your HTTP layer thin—exactly the Laravel-shaped promise, with async Python under the hood.
