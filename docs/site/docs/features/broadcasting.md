# Broadcasting

<a name="introduction"></a>
## Introduction

In many modern web applications, WebSockets are used to implement real-time, live-updating interfaces. When some data is updated on the server, a message is sent over a WebSocket connection to be handled by the client. Arvel's broadcasting publishes named events on named channels through a pluggable driver, so your frontend can subscribe and react in real time.

<a name="configuration"></a>
## Configuration

Broadcasting is configured through `BroadcastConfig` (the `BROADCASTING_*` environment variables):

```ini
BROADCASTING_DEFAULT=redis-pubsub
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
> The `pusher` driver is stubbed. Use `redis` for real-time delivery, or `log` / `null` in development and tests.

<a name="registering-the-provider"></a>
### Registering the Provider

Broadcasting is **opt-in**. Add `BroadcastServiceProvider` to `bootstrap/providers.py`. It binds the `Broadcast` facade; without it, the facade raises a runtime error.

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

<a name="testing"></a>
## Testing

`BroadcasterFake` records every `broadcast(...)` call so you can assert what was published, with no real driver involved. It exposes `calls` and `assert_broadcasted(event_name)`:

```python
from arvel.testing.broadcasting import BroadcasterFake

fake = BroadcasterFake()
await fake.broadcast(["orders.1"], "order.shipped", {"order_id": 1})

fake.assert_broadcasted("order.shipped")
assert fake.calls[0].payload == {"order_id": 1}
```

> [!NOTE]
> `BroadcasterFake` is a driver-level fake, not a manager — `Broadcast.set_manager(...)` expects a `BroadcastManager`. To route the `Broadcast` facade through the fake, wrap it in a test `BroadcastManager` whose `driver()` returns the fake.
