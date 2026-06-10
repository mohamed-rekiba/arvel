# Events

<a name="introduction"></a>
## Introduction

Arvel's events provide a simple observer pattern, letting you subscribe and listen for events in your application. **Events** are immutable Pydantic models (`Event` subclasses `BaseModel` with `frozen=True`); **listeners** react to them. A single event can have multiple listeners that don't depend on each other, which is a great way to decouple side effects from the code that triggers them.

<a name="quick-start"></a>
### Quick start

```python
# bootstrap/providers.py
from arvel.events.providers.event_service_provider import EventServiceProvider

providers = [EventServiceProvider, ...]
```

```python
# app/events/order_shipped.py
from arvel.events.event import Event


class OrderShipped(Event):
    order_id: int
    tracking_number: str
```

```python
# app/listeners/send_shipment_notification.py
from arvel.events.listener import Listener
from app.events.order_shipped import OrderShipped


class SendShipmentNotification(Listener[OrderShipped]):
    async def handle(self, event: OrderShipped) -> None:
        ...
```

Register the mapping in a service provider's `boot()` phase, then dispatch:

```python
from arvel.events.dispatcher import EventDispatcher
from arvel.facades.event import Event


async def boot(self) -> None:
    dispatcher = self.container.make(EventDispatcher)
    dispatcher.listen(OrderShipped, SendShipmentNotification)

# elsewhere in your app
await Event.dispatch(OrderShipped(order_id=1, tracking_number="1Z999"))
```

> [!NOTE]
> Import the `Event` facade from `arvel.facades.event` — not the `Event` base class from `arvel.events.event`. See [Facades](../core-concepts/facades.md#facades-in-their-own-modules).

<a name="registering-the-provider"></a>
## Registering the Provider

Events are **opt-in**. Add `EventServiceProvider` to `bootstrap/providers.py`. It binds the `Event` facade and wires the dispatcher to the container (so listeners can be resolved with dependency injection). See [Service Providers](../core-concepts/service-providers.md#opt-in-providers).

<a name="defining-events"></a>
## Defining Events

An event is a Pydantic model. Declare its payload as typed fields. Events are frozen (immutable) and auto-register themselves, so a queued listener can deserialize them later:

```python
from arvel.events.event import Event


class OrderShipped(Event):
    order_id: int
    tracking_number: str
```

<a name="defining-listeners"></a>
## Defining Listeners

A listener subclasses `Listener[E]` for its event type and implements an async `handle`:

```python
from arvel.events.listener import Listener
from app.events.order_shipped import OrderShipped


class SendShipmentNotification(Listener[OrderShipped]):
    async def handle(self, event: OrderShipped) -> None:
        # notify the customer
        ...
```

Because the dispatcher resolves listeners through the container, you can declare constructor dependencies and they'll be injected.

<a name="registering-listeners"></a>
## Registering Listeners

Map events to listeners on the dispatcher with `listen`. Registration is idempotent and order-preserving — listeners fire in the order they were registered. Do this in a service provider's boot phase:

```python
from arvel.events.dispatcher import EventDispatcher


async def boot(self) -> None:
    dispatcher = self.container.make(EventDispatcher)
    dispatcher.listen(OrderShipped, SendShipmentNotification)
```

> [!NOTE]
> There is no convention-based listener auto-discovery — register each event-to-listener mapping explicitly.

<a name="dispatching-events"></a>
## Dispatching Events

Dispatch an event instance through the `Event` facade. `dispatch` is a coroutine:

```python
from arvel.facades.event import Event

await Event.dispatch(OrderShipped(order_id=1, tracking_number="1Z999"))
```

Every registered listener runs. If one listener raises, the error is logged and the remaining listeners still run — one bad listener won't break the rest.

<a name="queued-listeners"></a>
## Queued Listeners

For slow work (sending mail, calling external APIs), push the listener onto the queue by mixing in `ShouldQueue`. Instead of running inline, the dispatcher enqueues it through the [`Bus`](queues.md):

```python
from arvel.events.listener import Listener
from arvel.events.should_queue import ShouldQueue


class SendShipmentNotification(Listener[OrderShipped], ShouldQueue):
    async def handle(self, event: OrderShipped) -> None:
        ...
```

> [!NOTE]
> If no queue is configured (`Bus` isn't bound), queued listeners run inline so events still fire in development. Once a queue *is* configured, the listener is always enqueued — a broker failure is logged (`queued_listener_enqueue_failed`), not silently run inline, so one hiccup can't double-run a listener or stall the publish loop. See [Queues](queues.md).

<a name="events-and-broadcasting"></a>
## Events & Broadcasting

An event that also implements the `ShouldBroadcast` contract is pushed to your broadcast driver after the synchronous listeners finish. See [Broadcasting](broadcasting.md#the-shouldbroadcast-contract).

Example — ship an order, notify listeners, then push to WebSocket clients:

```python
class OrderShipped(Event, ShouldBroadcast):
    order_id: int
    tracking_number: str

    def broadcast_on(self) -> list[str]:
        return [f"orders.{self.order_id}"]

    def broadcast_as(self) -> str:
        return "order.shipped"

    def broadcast_with(self) -> dict[str, object]:
        return {"order_id": self.order_id, "tracking_number": self.tracking_number}


async def ship_order(order: Order) -> None:
    order.status = "shipped"
    await order.save()
    await Event.dispatch(
        OrderShipped(order_id=order.id, tracking_number=order.tracking_number)
    )
    # inline listeners run first, then Broadcast.event() if BroadcastServiceProvider is registered
```

<a name="testing"></a>
## Testing

`Event.fake()` records dispatched events instead of running listeners, so you can assert they fired:

```python
with Event.fake():
    await ship_order(order)
    Event.assert_dispatched(OrderShipped)
    Event.assert_dispatched(OrderShipped, times=1)
    Event.assert_not_dispatched(OrderCancelled)
```
