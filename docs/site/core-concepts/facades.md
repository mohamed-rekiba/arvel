# Facades

<a name="introduction"></a>
## Introduction

Facades provide a "static" interface to services available in the application's [service container](service-container.md). Arvel ships many facades which provide access to almost all of the framework's features.

Arvel facades serve as concise gateways to the underlying services, providing the benefit of a terse, memorable syntax while maintaining more testability and flexibility than traditional static methods. Instead of resolving a manager from the container and calling it, you call a class method:

```python
from arvel.facades import Cache

await Cache.put("user:1", {"name": "Ada"}, ttl=3600)
user = await Cache.get("user:1")
```

Behind the scenes, `Cache` proxies to a `CacheManager` bound by `CacheServiceProvider`. The real object is still container-managed and swappable — which is exactly what the `fake()` helpers exploit in [testing](#facades-in-testing).

<a name="how-facades-work"></a>
## How Facades Work

Unlike some frameworks, Arvel has no single `Facade` base class or dynamic accessor magic. Each facade is a small, hand-written class that holds a reference to its underlying service (set when the service's provider registers or boots) and forwards calls to it. A few facades are backed by environment configuration or a module-level singleton rather than the container.

The practical upshot: a facade is a thin, explicit shortcut to a service. There's nothing dynamic to learn — but it does mean **import paths matter**, since facades live in different submodules.

<a name="facade-import-paths"></a>
## Facade Import Paths

> [!WARNING]
> Facades are **not** exported from the top-level `arvel` package. Import each from its module. Importing from the wrong path fails. Use the tables below.

<a name="the-arvel-facades-package"></a>
### The arvel.facades Package

```python
from arvel.facades import Cache, Config, Crypt, Http, Log, Session, Storage
from arvel.context import Context
```

| Facade | Backs | Provider required | Docs |
|---|---|---|---|
| `Config` | Typed config registry | `ConfigServiceProvider` (auto) | [Configuration](configuration.md) |
| `Cache` | `CacheManager` | `CacheServiceProvider` | [Cache](../features/cache.md) |
| `Storage` | `StorageManager` | `StorageServiceProvider` | [File Storage](../features/storage.md) |
| `Session` | `SessionManager` | `SessionServiceProvider` | [Sessions](../features/session.md) |
| `Crypt` | `Encrypter` (from `APP_KEY`) | none (reads env) | [Encryption](../features/encryption.md) |
| `Http` | Outbound HTTP client | none (stateless) | [HTTP Client](../features/http-client.md) |
| `Log` | OpenTelemetry logger | none (OTel-backed) | [Logging](../features/logging.md) |
| `Context` | Per-request context repository | none (ContextVar) | — (module-level facade) |

<a name="facades-in-their-own-modules"></a>
### Facades in Their Own Modules

```python
from arvel.facades.auth import Auth
from arvel.facades.event import Event
from arvel.facades.mail import Mail
from arvel.facades.notification import Notification
from arvel.facades.broadcast import Broadcast
from arvel.facades.bus import Bus
from arvel.facades.hash import Hash
from arvel.routing import Route, URL
```

| Facade | Backs | Provider required | Docs |
|---|---|---|---|
| `Auth` | `AuthManager` | `AuthServiceProvider` | [Authentication](../features/authentication.md) |
| `Event` | Event dispatcher | `EventServiceProvider` | [Events](../features/events.md) |
| `Mail` | `Mailer` | `MailServiceProvider` | [Mail](../features/mail.md) |
| `Notification` | `NotificationManager` | `NotificationServiceProvider` | [Notifications](../features/notifications.md) |
| `Broadcast` | `BroadcastManager` | `BroadcastServiceProvider` | [Broadcasting](../features/broadcasting.md) |
| `Bus` | Queue dispatcher | `QueueServiceProvider` | [Queues](../features/queues.md) |
| `Hash` | Argon2 password hasher | none | [Authentication](../features/authentication.md) |
| `Route` / `URL` | Router / URL generator | `HttpServiceProvider` (auto) | [Routing](../the-basics/routing.md) |

<a name="when-a-facade-is-available"></a>
## When a Facade Is Available

A facade works only once the service behind it is bound. Most are bound when their provider registers — some at `create()` time (e.g. `Cache`, `Storage`), some at boot (e.g. `Event`). Inside a route handler or a provider's `boot()`, that's already the case. In a standalone script, boot the app first (`await app.boot()`).

`Crypt`, `Hash`, `Log`, and `Context` are different: they're module-level singletons, available on import with no provider. Only `Crypt` reads the environment — it needs `APP_KEY`. `Hash` (argon2id), `Log` (OpenTelemetry), and `Context` (a ContextVar store) work as-is.

> [!WARNING]
> `Cache`, `Session`, `Storage`, and `Broadcast` are bound only when their providers are registered, and those providers are **not** part of the default set. Add `CacheServiceProvider` / `SessionServiceProvider` / `StorageServiceProvider` / `BroadcastServiceProvider` to `bootstrap/providers.py` first, or the facade raises `FacadeNotBoundError`. The same goes for `Auth`, `Mail`, `Bus`, `Event`, and `Notification` — register their [providers](service-providers.md#opt-in-providers).

<a name="facades-vs-dependency-injection"></a>
## Facades vs Dependency Injection

One of the primary benefits of dependency injection is the ability to swap implementations of the injected class. Both facades and [`dep()`](service-container.md#resolving-in-routes-with-dep) reach the same container, so the choice is mostly ergonomic:

- **Facades** are terse and convenient for one-off calls (`Cache.get(...)`, `Mail.to(...)`), with no constructor wiring.
- **`dep()`** makes a dependency explicit in a handler's signature, which some teams prefer for visibility and per-call testability.

A good rule of thumb: use facades for framework services, and inject your *own* services with `dep()`.

<a name="facades-in-testing"></a>
## Facades in Testing

Because a facade forwards to a swappable service, several facades provide a `fake()` that substitutes a recording test double and exposes assertion helpers:

```python
from arvel.facades import Cache, Storage
from arvel.facades.mail import Mail
from arvel.facades.event import Event

with Mail.fake() as mail, Cache.fake(), Storage.fake(), Event.fake():
    await client.post("/api/checkout", json={...})

    assert len(mail.sent) == 1
    Cache.assert_stored("cart:1")
    Storage.assert_exists("receipts/1.pdf")
    Event.assert_dispatched(OrderPlaced)
```

| Facade | `fake()` | Assertions |
|---|---|---|
| `Cache` | yes | `assert_stored`, `assert_missing` |
| `Storage` | yes | `assert_exists`, `assert_missing` |
| `Event` | yes | `assert_dispatched`, `assert_not_dispatched` |
| `Bus` | yes | `assert_dispatched`, `assert_not_dispatched` |
| `Notification` | yes | `assert_sent_to`, `assert_not_sent_to`, `assert_nothing_sent` |
| `Http` | yes | `assert_sent`, `assert_not_sent`, `recorded` |
| `Mail` | yes | `.sent` list |

For facades without a `fake()` (e.g. `Broadcast`, `Session`, `Crypt`), swap the underlying service directly — for instance, `Crypt.set_encrypter(...)` or `Broadcast.set_manager(...)`. See [Testing](../features/testing.md).
