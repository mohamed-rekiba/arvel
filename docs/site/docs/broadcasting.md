# Broadcasting

Broadcasting pushes server-side events to connected clients in real time — chat messages, presence updates, notifications, live dashboards. Arvel ships first-party broadcasting backed by [Reverb](https://github.com/laravel/reverb)-compatible WebSocket protocol, plus optional drivers for Pusher and Soketi.

## Configuration

```env
BROADCAST_DEFAULT=reverb

REVERB_HOST=0.0.0.0
REVERB_PORT=8080
REVERB_APP_ID=local
REVERB_APP_KEY=local-key
REVERB_APP_SECRET=local-secret
```

Multiple driver options ship out of the box:

| Driver | Use when |
|---|---|
| `reverb` | Self-hosted, low-friction, default |
| `pusher` | Managed service, no ops |
| `soketi` | Pusher-protocol-compatible self-hosted alternative |
| `log` | Tests and local dev — logs to stdout instead of broadcasting |
| `null` | Discards events; useful in CI |

## Broadcasting an event

```python
from pydantic import BaseModel
from arvel.broadcasting import broadcast_on, ShouldBroadcast


class MessageSent(BaseModel, ShouldBroadcast):
    user_id: int
    message: str

    @broadcast_on
    def channels(self) -> list[str]:
        return [f"chat.{self.user_id}"]
```

Fire it from anywhere:

```python
from arvel.facades import Event


await Event.dispatch(MessageSent(user_id=42, message="hello"))
```

If the event subclasses `ShouldBroadcast`, Arvel ships it to the configured driver in addition to running any in-process listeners.

## Channels

Arvel supports three channel types:

| Type | Visibility | Authorization |
|---|---|---|
| **Public** | Anyone can subscribe | None |
| **Private** | Authenticated users only | Channel auth callback must return `True` |
| **Presence** | Authenticated + tracks who's online | Channel auth callback must return user data |

Define channel auth in `app/routes/channels.py`:

```python
from arvel.broadcasting import Channel


@Channel.private("orders.{order_id}")
async def authorize_order(user, order_id: int) -> bool:
    order = await Order.find(order_id)
    return order is not None and order.customer_id == user.id


@Channel.presence("chat.{room_id}")
async def authorize_chat(user, room_id: int) -> dict | None:
    if not await user.can_join_room(room_id):
        return None
    return {"id": user.id, "name": user.name, "avatar": user.avatar_url}
```

## Client-side subscription

Use the [Laravel Echo](https://laravel.com/docs/13.x/broadcasting#installing-laravel-echo) client (works against Reverb out of the box):

```js
import Echo from 'laravel-echo';
import Pusher from 'pusher-js';

window.Pusher = Pusher;
window.Echo = new Echo({
  broadcaster: 'reverb',
  key: 'local-key',
  wsHost: 'localhost',
  wsPort: 8080,
  forceTLS: false,
  enabledTransports: ['ws'],
});

Echo.private(`orders.${orderId}`)
  .listen('.OrderShipped', (event) => {
    console.log('order shipped', event);
  });
```

## Running the Reverb server

```bash
uv run arvel reverb:start --host=0.0.0.0 --port=8080
```

For production, run it behind a TLS-terminating reverse proxy (Nginx or Caddy) on a dedicated port. Reverb is a separate process from your HTTP app and scales horizontally with Redis pub/sub as the cross-node fan-out:

```env
REVERB_SCALING_DRIVER=redis
REVERB_SCALING_REDIS_URL=redis://redis.internal:6379/2
```

## Testing broadcasts

```python
from arvel.facades import Event


async def test_message_broadcasts() -> None:
    Event.fake([MessageSent])
    await dispatch_message(...)
    Event.assert_dispatched(MessageSent, lambda e: e.user_id == 42)
```

When `Event.fake()` includes a broadcast event, the broadcast doesn't actually fire — the recorder captures the intent.

## Where to next?

- [Events](events.md) — synchronous in-process events.
- [Notifications](notifications.md) — multi-channel notifications including broadcast.
