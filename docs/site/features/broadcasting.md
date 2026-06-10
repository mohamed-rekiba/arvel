# Broadcasting

<a name="introduction"></a>
## Introduction

In many modern web applications, WebSockets are used to implement real-time, live-updating interfaces. When some data is updated on the server, a message is sent over a WebSocket connection to be handled by the client. Arvel's broadcasting publishes named events on named channels through a pluggable driver, so your frontend can subscribe and react in real time.

<a name="quick-start"></a>
### Quick start

```python
# bootstrap/providers.py
from arvel.providers.broadcast_provider import BroadcastServiceProvider

providers = [BroadcastServiceProvider, ...]
```

```ini
# .env — log driver for local dev; redis-pubsub for real-time
BROADCASTING_DEFAULT=log
```

```python
from arvel.facades.broadcast import Broadcast

await Broadcast.send(
    channels=["orders.1"],
    event="order.updated",
    payload={"status": "shipped"},
)
```

Or tie broadcasting to the [events](events.md) system — dispatch an event that mixes in `ShouldBroadcast` and the dispatcher pushes it after listeners finish:

```python
from arvel.events.event import Event
from arvel.broadcasting.should_broadcast import ShouldBroadcast
from arvel.facades.event import Event as EventFacade


class OrderUpdated(Event, ShouldBroadcast):
    order_id: int
    status: str

    def broadcast_on(self) -> list[str]:
        return [f"orders.{self.order_id}"]

    def broadcast_as(self) -> str:
        return "order.updated"

    def broadcast_with(self) -> dict[str, object]:
        return {"order_id": self.order_id, "status": self.status}


await EventFacade.dispatch(OrderUpdated(order_id=1, status="shipped"))
```

<a name="configuration"></a>
## Configuration

Broadcasting reads `config/broadcasting.py` when present; the `BROADCASTING_*` environment variables are the fallback for any key the file doesn't set (see [the cascade](../core-concepts/configuration.md#the-cascade)):

```ini
BROADCASTING_DEFAULT=redis-pubsub
BROADCASTING_AUTH_ENDPOINT=/broadcasting/auth
```

<a name="drivers"></a>
### Drivers

| Driver | Behavior |
|---|---|
| `log` | Writes broadcasts to the log — good for local development |
| `null` | Discards broadcasts (default) |
| `redis-pubsub` | Publishes over Redis pub/sub |
| `pusher` | Pusher-compatible service |

> [!WARNING]
> The `pusher` driver is stubbed. Use `redis-pubsub` for real-time delivery, or `log` / `null` in development and tests.

<a name="registering-the-provider"></a>
### Registering the Provider

Broadcasting is **opt-in**. Add `BroadcastServiceProvider` to `bootstrap/providers.py`. It binds the `Broadcast` facade; without it, the facade raises a runtime error. See [Service Providers](../core-concepts/service-providers.md#opt-in-providers).

<a name="broadcasting-events"></a>
## Broadcasting Events

<a name="the-shouldbroadcast-contract"></a>
### The ShouldBroadcast Contract

To make an event broadcastable, implement the `ShouldBroadcast` contract. It defines what channels to broadcast on, the event name, and the payload:

```python
from collections.abc import Mapping, Sequence
from arvel.events.event import Event
from arvel.broadcasting.should_broadcast import ShouldBroadcast


class OrderShipped(Event, ShouldBroadcast):
    order_id: int

    def broadcast_on(self) -> Sequence[str]:
        return [f"orders.{self.order_id}"]

    def broadcast_as(self) -> str:
        return "order.shipped"

    def broadcast_with(self) -> Mapping[str, object]:
        return {"order_id": self.order_id}
```

> [!NOTE]
> If you don't override `broadcast_with`, the default uses the event's JSON dump (`model_dump(mode="json")` for `BaseModel`/`Event` events). That keeps rich fields like `datetime`, `UUID`, and `Decimal` JSON-safe — the drivers serialize the payload as JSON, so a raw Python dump would fail to send.

<a name="broadcasting-from-an-event"></a>
### Broadcasting From an Event

When you dispatch an [event](events.md) that implements `ShouldBroadcast`, the dispatcher pushes it to the broadcast driver automatically — after the synchronous listeners finish:

```python
from arvel.facades.event import Event

await Event.dispatch(OrderShipped(order_id=1))   # listeners run, then it broadcasts
```

> [!NOTE]
> Auto-broadcast only fires when the `Broadcast` facade is bound. If broadcasting isn't registered, the event still dispatches to listeners and the broadcast is silently skipped.

<a name="broadcasting-directly"></a>
### Broadcasting Directly

You can also publish without an event, straight through the facade:

```python
from arvel.facades.broadcast import Broadcast

await Broadcast.send(
    channels=["orders.1"],
    event="order.shipped",
    payload={"order_id": 1},
)

# Or push a ShouldBroadcast object explicitly:
await Broadcast.event(OrderShipped(order_id=1))
```

<a name="channels-and-authorization"></a>
## Channels & Authorization

Register an authorization callback for a channel pattern with the `Broadcast.channel` decorator. The callback decides whether a given user may listen on a channel:

```python
@Broadcast.channel("orders.{order_id}")
async def authorize_order(user: User, order_id: int) -> bool:
    return await Order.where(id=order_id, user_id=user.id).exists()
```

Channel authorization callbacks are registered on a module-level registry (`Broadcast.registry()`). Wire them during app boot — typically in the same service provider that registers your routes. The auth endpoint defaults to `/broadcasting/auth` (`BROADCASTING_AUTH_ENDPOINT`).

<a name="testing"></a>
## Testing

`BroadcasterFake` records every `broadcast(...)` call so you can assert what was published, with no real driver involved:

```python
from arvel.testing.broadcasting import BroadcasterFake
from arvel.broadcasting.config import BroadcastConfig, BroadcastDriver
from arvel.broadcasting.manager import BroadcastManager
from arvel.facades.broadcast import Broadcast

fake = BroadcasterFake()
manager = BroadcastManager(BroadcastConfig(default=BroadcastDriver.NULL))
# Swap the manager's driver in tests — or inject fake via Broadcast.set_manager(...)
Broadcast.set_manager(manager)

await fake.broadcast(["orders.1"], "order.shipped", {"order_id": 1})
fake.assert_broadcasted("order.shipped")
fake.assert_broadcasted_on("orders.1", "order.shipped")
assert fake.calls[0].payload == {"order_id": 1}
```

> [!NOTE]
> `BroadcasterFake` is a driver-level fake, not a manager. To route the `Broadcast` facade through it in integration tests, wrap it in a `BroadcastManager` whose `driver()` returns the fake, then call `Broadcast.set_manager(...)`. Event-driven broadcasts (`Event.dispatch` on a `ShouldBroadcast` event) go through the same path once `BroadcastServiceProvider` is registered.
