# Broadcasting

[Events](events.md) let one part of your app react to something that happened in another.
Broadcasting takes the same idea across the network boundary: the *browser* reacts too. When an
order ships, a message lands in a chat, or a long job finishes, you dispatch an event on the
server and it arrives in every connected client in real time — no polling, no refresh.

The wiring is deliberately small. An event opts in by subclassing `ShouldBroadcast` and naming
the channels it goes out on; the dispatcher routes it to the `broadcast` manager, which sends it
over the configured driver. Broadcasting is part of the **core** — nothing to install. The
websocket transport that carries messages to browsers is a driver extra; core
ships a `log` driver for dev/test and a `redis` driver that publishes over the [Redis](cache.md)
connection.

This page covers when to broadcast, marking and dispatching an event, the channel types and their
authorization, excluding the sender, drivers and config, and how it all fits together.

## When to broadcast

Broadcast when a server-side event needs to reach clients that aren't the one that triggered it:

- **Live updates** — a dashboard tile, a notification bell, a "someone is typing…" indicator.
- **Chat and collaboration** — a message or edit that every participant should see immediately.
- **Progress** — a queued import or export reporting back as it runs.

If the client that made the request is the only one that needs the result, you don't need
broadcasting — return it in the HTTP response. Broadcasting earns its keep when the update has to
reach *other* clients, out of band.

## Marking an event to broadcast

Any event becomes a broadcast by subclassing `ShouldBroadcast` and declaring its channels in
`broadcast_on()`:

```python
from dataclasses import dataclass
from arvel.events import ShouldBroadcast

@dataclass
class OrderShipped(ShouldBroadcast):
    order: Order

    def broadcast_on(self):
        return [f"orders.{self.order.id}"]
```

Dispatch it through the [`Event`](events.md) facade like any other event — listeners still run,
*and* the event goes out on its channels:

```python
from arvel import Event

await Event.dispatch(OrderShipped(order=order))
```

That's the whole happy path. The event is queued to a worker and delivered on channel
`orders.42`; any client subscribed to that channel receives it.

### Shaping the wire message

By default the message carries the event's class name and an empty payload. Two optional hooks
override each:

```python
@dataclass
class OrderShipped(ShouldBroadcast):
    order: Order

    def broadcast_on(self):
        return [f"orders.{self.order.id}"]

    def broadcast_as(self):
        return "order.shipped"        # wire event name (default: the class name, "OrderShipped")

    def broadcast_with(self):
        return {"id": self.order.id, "eta": self.order.eta.isoformat()}   # default: {}
```

Keep `broadcast_with()` to the fields the client needs — it's serialized onto the wire, so send
identifiers and display data, not whole models.

## Channels

`broadcast_on()` may return plain strings — which map straight to the wire name — or typed channel
objects. The three types differ only in their wire prefix and whether subscribing needs
authorization:

```python
from arvel.broadcasting import Channel, PrivateChannel, PresenceChannel

Channel("orders.42")          # → "orders.42"          public, anyone may subscribe
PrivateChannel("orders.42")   # → "private-orders.42"  subscriber must be authorized
PresenceChannel("room.7")     # → "presence-room.7"    authorized, and reports who's here
```

| Type | Wire prefix | Authorization | Use it for |
|------|-------------|---------------|------------|
| `Channel` | *(none)* | none | public, non-sensitive updates |
| `PrivateChannel` | `private-` | callback returning `bool` | data only some users may see |
| `PresenceChannel` | `presence-` | callback returning member data (`dict`) | channels where you also want the roster |

A bare string in `broadcast_on()` is a public channel — reach for `PrivateChannel` /
`PresenceChannel` the moment a channel carries anything a user shouldn't see uninvited.

## Authorizing private & presence channels

A private or presence channel is worthless if any client can subscribe to it. Before a browser
joins one, its websocket client `POST`s to the `/broadcasting/auth` endpoint, which runs a
server-side callback you register per channel pattern. Register callbacks from a provider's
`boot()` on the `broadcast` manager:

```python
class BroadcastServiceProvider(ServiceProvider):
    def boot(self):
        broadcast = self.app.make("broadcast")

        # private: return truthy to allow, falsy to deny
        broadcast.channel("orders.{id}", lambda user, id: user.owns_order(int(id)))

        # presence: return the member data to publish to the channel's roster
        broadcast.channel(
            "room.{room}",
            lambda user, room: {"id": user.id, "name": user.name},
        )
```

The pattern is matched against the **bare** channel name — the `private-` / `presence-` prefix is
stripped first — and each `{placeholder}` becomes a positional argument after `user`, in order.
The endpoint sits behind the [authentication](auth/authentication.md) middleware, so `user` is
always a real authenticated user, never `None`; a guest never reaches your callback. The first
pattern that matches wins; no match, or a falsy return, is a `403`.

For presence channels, return a `dict` of the data other members should see — even an empty `{}`
authorizes (it means "joined, no metadata"). Only `False` or `None` denies. Callbacks may be sync
or async.

!!! note "The `/broadcasting/auth` endpoint lives in routing, not broadcasting"
    It needs both the authenticated user *and* your channel callbacks, and broadcasting sits below
    auth in the module graph — it must never import it. Routing is the top layer, so it wires the
    two together without either side depending on the other. `RoutingServiceProvider` registers
    the route automatically; you only write the callbacks.

## Excluding the sender — `to_others()`

When a user sends a chat message, they've already rendered it locally — echoing the broadcast back
to them draws it twice. Mix in `InteractsWithSockets` and call `to_others()` to exclude the
socket that triggered the event:

```python
from arvel.events import ShouldBroadcast
from arvel.broadcasting import InteractsWithSockets

@dataclass
class MessageSent(ShouldBroadcast, InteractsWithSockets):
    message: Message

    def broadcast_on(self):
        return [PrivateChannel(f"chat.{self.message.chat_id}")]

# in the handler:
await Event.dispatch(MessageSent(message=msg).to_others())
```

`to_others()` reads the sender's socket id from the current request's `X-Socket-ID` header. Your
app binds that once, where it reads the header, so broadcasting never has to reach up into HTTP:

```python
from arvel.broadcasting import bind_socket_id

bind_socket_id(request.header("X-Socket-ID"))   # before dispatching
```

The excluded socket id travels in the message; every subscriber *except* that one delivers it.

### Conditional broadcasts — `broadcast_when()`

`InteractsWithSockets` also gives you `broadcast_when()` to suppress a broadcast unless a condition
holds at dispatch time:

```python
await Event.dispatch(
    OrderShipped(order=order).broadcast_when(lambda: order.notifiable)
)
```

The condition is evaluated **once, at dispatch** — not on the worker. A queued broadcast can't
carry a closure, so if the condition is false the event is dropped before it's ever enqueued.

## Queued vs. inline

By default a broadcast is **queued**: dispatching returns immediately, and a small internal job
carries the delivery to a [queue worker](queues.md). Better still, the enqueue rides
[after-commit](events.md#after-commit-events-shoulddispatchaftercommit) — a broadcast dispatched
inside `db.transaction()` is only sent if the transaction commits, so you never announce an order
that rolled back.

When you need the send to happen inline, during dispatch, subclass `ShouldBroadcastNow` instead:

```python
from arvel.events import ShouldBroadcastNow

@dataclass
class ServerHeartbeat(ShouldBroadcastNow):   # sent right now, never queued, never deferred
    def broadcast_on(self):
        return ["ops.heartbeat"]
```

If no queue is configured, a plain `ShouldBroadcast` falls back to sending inline too — so the
same code works before you've stood up a worker; wiring one up moves the delivery off the request
path with no change to the event.

## Drivers & configuration

The active driver is `broadcasting.default`; core ships two:

```toml
# config — broadcasting section
[broadcasting]
default = "log"     # "log" (dev/test) or "redis"
```

| Driver | What it does |
|--------|--------------|
| `log` | Records each broadcast in memory, sends nothing over the network. The default — ideal for dev and tests, where you assert on what *would* have gone out. |
| `redis` | Publishes each broadcast as one JSON message per channel over the [Redis](cache.md) connection, under the `arvel.broadcasting.<channel>` key. A websocket server subscribes to Redis and fans messages out to browsers. |

The `redis` driver's message body is `{"event", "data", "except_socket_id"}` — the wire name from
`broadcast_as()`, the payload from `broadcast_with()`, and the socket to skip from `to_others()`.
The websocket transport that turns those Redis messages into browser deliveries is a separate
driver extra; core stops at publishing.

## Common mistakes & gotchas

- **Forgetting `broadcast_on()`.** An event with no `broadcast_on()` broadcasts on *no* channels —
  it's dispatched and silently goes nowhere. If clients see nothing, check the channel list first.
- **A public channel for private data.** A bare string is a `Channel` — anyone can subscribe. Use
  `PrivateChannel` and a `channel()` callback for anything a user shouldn't see uninvited.
- **Truthiness in a presence callback.** Return the member `dict` (even `{}`) to authorize; return
  `False`/`None` to deny. Don't return `0` or `""` meaning "allow" — only `False` and `None` deny,
  but relying on that is a foot-gun. Be explicit.
- **Expecting a queued broadcast in a test with no queue.** With no queue bound, `ShouldBroadcast`
  sends inline; with a `FakeQueue`, the delivery is a job you assert was pushed. Use the `log`
  driver and inspect its recorded sends, or a fake queue — don't assert against a real transport.
- **Broadcasting before commit.** A plain `ShouldBroadcast` already defers its enqueue to
  after-commit; but if you send with `ShouldBroadcastNow` inside a transaction, the message goes
  out immediately — before the row exists for anyone who reacts to it.
- **An empty `app.key`.** The `/broadcasting/auth` endpoint signs its response with an HMAC keyed
  by `app.key`. An empty key makes that signature forgeable, so the endpoint refuses with a `500`
  rather than hand out a weak one. Set a real key.

## How it works

The dispatcher checks each dispatched event: if it's a `ShouldBroadcast`, it's routed to
`_broadcast` *before* the normal listeners run. There, `broadcast_when()` is evaluated once; a
false condition drops the event. A `ShouldBroadcastNow` is sent inline immediately. Otherwise, if
a `broadcast_dispatcher` is bound — the queue provider binds it, the same seam a `ShouldQueue`
listener uses — the send is wrapped in an after-commit callback that enqueues a `CallQueuedBroadcast`
job. The job encodes the event as a `{class, state}` view (the same rail a queued mailable or
notification rides), and on the worker decodes it and re-sends through the `broadcast` manager.

The manager resolves the configured driver and calls its `broadcast(event)`. The `log` driver
appends to an in-memory list; the `redis` driver serializes the payload once and `publish`es it
per channel. Both read the channel names, wire name, and payload through the same small helpers
(`channels_for`, `event_name`, `broadcast_payload`), so a driver never has to know how an event
declares them.

Channel authorization is a separate registry on the manager: `channel(pattern, callback)` compiles
each pattern into an anchored regex with one capture group per `{placeholder}`. When
`/broadcasting/auth` calls `authorize(channel_name, user)`, it strips the prefix, finds the first
matching pattern, and runs its callback with the captured segments. The endpoint returns an
HMAC-SHA256 signature over `socket_id:channel_name` (plus the member `dict` for a presence
channel), which the client presents to the websocket server as proof it was authorized.

Broadcasting sits low in the module graph and imports neither auth, HTTP, nor the queue directly —
each of those crosses into broadcasting through a container-bound seam (`bind_socket_id`,
`broadcast_dispatcher`, the routing-owned auth endpoint), which is why the pieces compose without
a dependency cycle.

## See also

- [Events](events.md) — broadcasting rides the event dispatcher; start here for dispatch, queued
  listeners, and after-commit.
- [Queues & Jobs](queues.md) — where a queued broadcast is delivered.
- [Notifications](notifications.md#the-broadcast-channel) — the `broadcast` notification channel
  sends a `BroadcastNotification` event through this same manager.
- [Authentication](auth/authentication.md) — the `/broadcasting/auth` endpoint runs behind it.
- [Cache & Redis](cache.md) — the connection the `redis` driver publishes over.
