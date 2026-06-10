# Features

Optional subsystems behind facades and service providers. Most are **opt-in** — add the provider to `bootstrap/providers.py` before the facade works.

## By category

### Auth & security

| Feature | Provider | Doc |
|---|---|---|
| Authentication | `AuthServiceProvider` | [authentication.md](authentication.md) |
| Authorization | (via Auth) | [authorization.md](authorization.md) |
| Encryption | none (`APP_KEY`) | [encryption.md](encryption.md) |
| Session | `SessionServiceProvider` | [session.md](session.md) |

### Data & I/O

| Feature | Provider | Doc |
|---|---|---|
| Cache | `CacheServiceProvider` | [cache.md](cache.md) |
| Storage | `StorageServiceProvider` | [storage.md](storage.md) |
| HTTP Client | none | [http-client.md](http-client.md) |
| Date & Time | none | [datetime.md](datetime.md) |
| Localization | auto | [localization.md](localization.md) |

### Messaging & async

| Feature | Provider | Doc |
|---|---|---|
| Mail | `MailServiceProvider` | [mail.md](mail.md) |
| Notifications | `NotificationServiceProvider` | [notifications.md](notifications.md) |
| Events | `EventServiceProvider` | [events.md](events.md) |
| Queues | `QueueServiceProvider` | [queues.md](queues.md) |
| Broadcasting | `BroadcastServiceProvider` | [broadcasting.md](broadcasting.md) |
| Scheduling | auto | [scheduling.md](scheduling.md) |

### Operations

| Feature | Doc |
|---|---|
| Logging | [logging.md](logging.md) |
| Maintenance mode | [maintenance-mode.md](maintenance-mode.md) |
| Testing | [testing.md](testing.md) |

> Baseline providers (config, database, HTTP, scheduler) register automatically — see [Framework providers](../core-concepts/service-providers.md#auto-registered-providers).

## Typical wiring

```python
# bootstrap/providers.py
from arvel.auth.provider import AuthServiceProvider
from arvel.providers.cache_provider import CacheServiceProvider
from arvel.queue.providers.queue_service_provider import QueueServiceProvider

providers = [
    CacheServiceProvider,
    AuthServiceProvider,
    QueueServiceProvider,
    AppServiceProvider,
]
```

Companion packages ([OAuth](../packages/oauth.md), [Permission](../packages/permission.md), …) follow the same pattern with their own providers.

## See also

- [Facades](../core-concepts/facades.md) — import paths and `fake()` helpers.
- [CLI](../cli/commands.md) — queue, schedule, cache, and auth commands.
