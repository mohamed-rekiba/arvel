# Service Providers

<a name="introduction"></a>
## Introduction

Service providers are the central place of all Arvel application bootstrapping. Your own application, as well as all of Arvel's core services, are bootstrapped via service providers.

But what do we mean by "bootstrapped"? In general, we mean **registering** things: registering container bindings, event listeners, middleware, and routes. Service providers are the central place to configure your application.

If you open `bootstrap/providers.py`, you'll see your application's providers list. Each provider gives you a place to wire one slice of your application together.

<a name="quick-start"></a>
### Quick start — a minimal provider

```python
# app/providers/app_service_provider.py
from arvel.providers import ServiceProvider
from app.repositories.post_repository import PostRepository
from app.services.post_service import PostService


class AppServiceProvider(ServiceProvider):
    def register(self) -> None:
        self.container.singleton(PostRepository)
        self.container.singleton(PostService)

    async def boot(self) -> None:
        pass
```

```python
# bootstrap/providers.py
from app.providers.app_service_provider import AppServiceProvider

providers: list[type[ServiceProvider]] = [
    AppServiceProvider,
]
```

<a name="writing-service-providers"></a>
## Writing Service Providers

All service providers extend the `ServiceProvider` class. Most contain a `register` and a `boot` method. Generate a new provider with the `make:provider` command:

```bash
arvel make:provider AppServiceProvider
```

A provider receives the `Application` in its constructor and exposes it as `self.app`, with the root container as `self.container`:

```python
from arvel.providers import ServiceProvider


class AppServiceProvider(ServiceProvider):
    def register(self) -> None:
        self.container.singleton(InventoryService)

    async def boot(self) -> None:
        ...

    async def shutdown(self) -> None:
        ...
```

<a name="the-register-method"></a>
### The Register Method

Within the `register` method, you should **only bind things into the [container](service-container.md)**. The `register` method is synchronous and runs during the application's build step, before any other provider has booted. You should never attempt to register event listeners, do I/O, resolve another provider's service, or perform any other side effect within the `register` method — those services may not be bound yet.

```python
def register(self) -> None:
    self.container.singleton(PaymentGateway, StripeGateway)
```

<a name="the-boot-method"></a>
### The Boot Method

The `boot` method is asynchronous and is called after *all* other service providers have been registered, meaning you have access to every binding the framework and your app have registered. This is the place for wiring that depends on other services — attaching listeners, registering broadcast channels, opening connections:

```python
from arvel.events.dispatcher import EventDispatcher


async def boot(self) -> None:
    # OrderPlaced is your event; SendOrderConfirmation your listener.
    dispatcher = self.container.make(EventDispatcher)
    dispatcher.listen(OrderPlaced, SendOrderConfirmation)
```

<a name="the-shutdown-method"></a>
### The Shutdown Method

The `shutdown` method runs on application teardown, in **reverse** registration order. Release any resources your provider opened:

```python
async def shutdown(self) -> None:
    await self._connection.close()
```

<a name="provider-members"></a>
### Provider Members

| Member | Purpose |
|---|---|
| `self.app` | The `Application`. |
| `self.container` | The root [container](service-container.md). |
| `subsystem` | `ClassVar[CliSubsystem \| None]`. Tags the provider for the [needs-based CLI bootstrap](../cli/commands.md#needs-based-bootstrap). Baseline framework providers set this explicitly; user providers leave it `None` and behave as the `USER_PROVIDERS` bucket. |
| `register()` | Sync. Register container bindings only. |
| `boot()` | Async. Startup wiring after all providers register. |
| `shutdown()` | Async. Teardown, reverse order. |
| `commands()` | Return CLI command classes/instances this provider contributes. |
| `publishes(paths, *, tag=, is_migrations=)` | Declare files an app can copy out with `vendor:publish`. |
| `safe_config(cls, *, default)` | Resolve a config object, falling back to `default` if it isn't available. |

See [Request Lifecycle](lifecycle.md#the-register-and-boot-phases) for the full register-vs-boot ordering.

<a name="registering-providers"></a>
## Registering Providers

All service providers are registered in the `bootstrap/providers.py` file. This file exposes a `providers` list:

```python
from arvel.providers import ServiceProvider
from app.providers.app_service_provider import AppServiceProvider

providers: list[type[ServiceProvider]] = [
    AppServiceProvider,
]
```

Your providers run after the framework's baseline providers, so framework services are already bound by the time your `register()` runs.

<a name="contributing-cli-commands"></a>
## Contributing CLI Commands

A provider exposes console commands by returning them from `commands()`. The framework collects them from every provider when the app boots:

```python
class AppServiceProvider(ServiceProvider):
    def commands(self) -> list[type]:
        return [SyncInventoryCommand]
```

You may return command **classes** (instantiated with no arguments) or pre-built command **instances** (useful when a command needs injected dependencies). See [CLI Commands](../cli/commands.md).

Provider-contributed commands only register when the framework actually boots the provider. With the needs-based bootstrap, that means the dispatched command's `requires` must include the subsystem your provider serves (or `USER_PROVIDERS` for user-app providers). Declare what your command needs:

```python
from typing import ClassVar

from arvel.console import Command, Context
from arvel.console._subsystem import CliSubsystem


class SyncInventoryCommand(Command):
    name: ClassVar[str] = "inventory:sync"
    help: ClassVar[str] = "Sync inventory with the warehouse API"
    requires: ClassVar[frozenset[CliSubsystem]] = frozenset(
        {CliSubsystem.DATABASE, CliSubsystem.USER_PROVIDERS}
    )

    def handle(self, ctx: Context) -> int:
        ...
```

Most user-app commands need `USER_PROVIDERS` so the provider that registered them actually runs. Add `DATABASE`, `QUEUE`, or whichever subsystems your handler touches — the bootstrap computes the transitive closure for you (`QUEUE` already pulls in `DATABASE`).

<a name="publishing-assets"></a>
## Publishing Assets

Package authors declare files an application can copy into its own tree. Call `publishes` from `boot`, mapping source paths to destinations:

```python
from pathlib import Path


async def boot(self) -> None:
    package_root = Path(__file__).parent
    self.publishes(
        {package_root / "migrations": "database/migrations"},
        tag="my-package",
        is_migrations=True,
    )
```

There's no `self.package_path` — resolve your package directory yourself (here, from the provider module's own `__file__`).

Applications then copy them out:

```bash
arvel vendor:publish --tag=my-package
```

<a name="framework-providers-reference"></a>
## Framework Providers Reference

<a name="auto-registered-providers"></a>
### Auto-Registered Providers

These baseline providers register automatically — you don't list them, but knowing they exist explains where framework bindings come from:

| Provider | Binds / does |
|---|---|
| `ConfigServiceProvider` | `Config` accessor; one singleton per registered `ArvelSettings`. |
| `LogServiceProvider` | No-op placeholder; the OpenTelemetry-backed `Log` facade is bootstrapped by `ObservabilityServiceProvider`. |
| `LangServiceProvider` | Translator for [localization](../features/localization.md). |
| `ContextServiceProvider` | Per-request context store (the [`Context` facade](facades.md)). |
| `ObservabilityServiceProvider` | Tracing, logging, metrics. |
| `DatabaseServiceProvider` | Async engine, session maker, `AsyncSession`, `Schema`. |
| `HttpServiceProvider` | `Router`, exception handler, rate-limiter store, maintenance manager. |
| `SchedulerServiceProvider` | `Schedule`, scheduler kernel; discovers `app/console/kernel.py`. |
| `ConsoleServiceProvider` | Collects every provider's `commands()` (always registered last). |

<a name="opt-in-providers"></a>
### Opt-In Providers

Many subsystems are **not** auto-registered. Add their provider to `bootstrap/providers.py` to use them, or their [facade](facades.md) raises `FacadeNotBoundError` (or a `RuntimeError`):

| Provider | Import | Enables |
|---|---|---|
| `CacheServiceProvider` | `arvel.providers.cache_provider` | [`Cache`](../features/cache.md) |
| `SessionServiceProvider` | `arvel.providers.session_provider` | [`Session`](../features/session.md) |
| `StorageServiceProvider` | `arvel.providers.storage_provider` | [`Storage`](../features/storage.md) |
| `BroadcastServiceProvider` | `arvel.providers.broadcast_provider` | [`Broadcast`](../features/broadcasting.md) |
| `AuthServiceProvider` | `arvel.auth.provider` | [`Auth`](../features/authentication.md), [`Gate`](../features/authorization.md), auth routes |
| `MailServiceProvider` | `arvel.mail.providers.mail_service_provider` | [`Mail`](../features/mail.md) |
| `QueueServiceProvider` | `arvel.queue.providers.queue_service_provider` | [`Bus`](../features/queues.md), queue commands |
| `EventServiceProvider` | `arvel.events.providers.event_service_provider` | [`Event`](../features/events.md) |
| `NotificationServiceProvider` | `arvel.notifications.providers.notification_service_provider` | [`Notification`](../features/notifications.md) |

```python
from arvel.providers.cache_provider import CacheServiceProvider
from arvel.providers.storage_provider import StorageServiceProvider

providers: list[type[ServiceProvider]] = [
    CacheServiceProvider,
    StorageServiceProvider,
    AppServiceProvider,
]
```

> [!NOTE]
> Companion packages (`arvel-oauth`, `arvel-permission`, …) are not auto-registered either. Add their provider to `bootstrap/providers.py` yourself. See the [packages overview](../packages/README.md).

<a name="provider-ordering"></a>
### Provider Ordering

The framework resolves the provider chain in a fixed order: the baseline **head** providers (config, logging, language, context, observability, database, HTTP, scheduler) run first, then **your** providers in the order you list them, and finally the `ConsoleServiceProvider` is forced last so it can collect commands from everything else. Duplicate entries are de-duplicated, so re-listing a baseline provider is a harmless no-op.
