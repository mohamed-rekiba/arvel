# Service Providers

Service providers are Arvel’s way of grouping bootstrapping logic the way Laravel does — one class per concern, a **`register`** pass for bindings, a **`boot`** pass for wiring that needs a live application. Keeps `bootstrap/providers.py` readable and gives you a single place to look when something stops resolving.

## The `ServiceProvider` base class

Subclass `ServiceProvider`, set an optional **`priority`** (lower numbers run earlier), and implement the hooks you need. The framework handles ordering, error wrapping, and shutdown.

```python
from arvel.foundation.provider import ServiceProvider
from arvel.foundation.container import ContainerBuilder
from arvel.foundation.application import Application

class BillingServiceProvider(ServiceProvider):
    priority = 40  # after framework defaults unless you need earlier

    async def register(self, container: ContainerBuilder) -> None:
        ...

    async def boot(self, app: Application) -> None:
        ...

    async def shutdown(self, app: Application) -> None:
        ...
```

### `register()` — bindings only

`register` receives a **`ContainerBuilder`**. Wire interfaces to implementations, factories, or static values here. Do **not** resolve services yet — the container is not fully built, and other providers have not had their say.

### `boot()` — integration time

`boot` receives the fully configured **`Application`**: settings, built `Container`, FastAPI app, base path, etc. Register routes, listeners, or kernel middleware when you need the world to exist. Framework providers use this phase to discover routes and mount the HTTP kernel.

### `shutdown()` — optional cleanup

Override `shutdown` to close sockets, flush pools, or stop background tasks. The kernel calls providers in **reverse** order during `Application.shutdown()`.

## Registering providers

Every Arvel application must ship a **`bootstrap/providers.py`** file at the project root. Export a list named **`providers`** containing provider classes (not instances). Arvel imports the module dynamically, instantiates each class, sorts by `priority`, and runs the lifecycle.

```python
# bootstrap/providers.py
from arvel.data.provider import DataServiceProvider
from arvel.http.provider import HttpServiceProvider
from arvel.infra.provider import InfrastructureProvider

from app.providers.billing import BillingServiceProvider

providers = [
    InfrastructureProvider,
    DataServiceProvider,
    HttpServiceProvider,
    BillingServiceProvider,
]
```

If the file is missing or `providers` is undefined, boot fails fast with `ProviderNotFoundError` — better than silently running without half your stack.

## Creating a custom provider

Start small: one binding, one `boot` side effect. Expand when the module grows.

```python
from arvel.foundation.container import ContainerBuilder, Scope
from arvel.foundation.provider import ServiceProvider
from arvel.foundation.application import Application

from app.billing import BillingGateway, StripeGateway

class BillingServiceProvider(ServiceProvider):
    priority = 45

    async def register(self, container: ContainerBuilder) -> None:
        container.provide(BillingGateway, StripeGateway, scope=Scope.REQUEST)

    async def boot(self, app: Application) -> None:
        # Example: read typed module settings, subscribe to events, warm caches.
        from arvel.http.config import HttpSettings

        http = app.settings(HttpSettings)
        # Use `http` for route registration, event subscribers, or guards that
        # need HTTP settings once the app is fully booted.
```

Use any `ModuleSettings` subclass your app registers — `app.settings(...)` only works after the application has finished booting.

## `InfrastructureProvider` as a reference

The framework ships `InfrastructureProvider` (`arvel.infra.provider`) to show how multi-driver infrastructure should look. It binds **contract types** (`CacheContract`, `MailContract`, `StorageContract`, `LockContract`) to factory callables that read each subsystem’s settings and return the right driver — memory cache, Redis, SMTP, S3, and so on.

```python
from arvel.foundation.container import ContainerBuilder, Scope
from arvel.foundation.provider import ServiceProvider
from arvel.cache.contracts import CacheContract
from arvel.mail.contracts import MailContract

class InfrastructureProvider(ServiceProvider):
    priority = 10

    async def register(self, container: ContainerBuilder) -> None:
        container.provide_factory(CacheContract, _make_cache, scope=Scope.APP)
        container.provide_factory(MailContract, _make_mail, scope=Scope.APP)
```

Factories stay private to the module; the public surface remains the contracts. The same provider also implements `shutdown` to gracefully close async clients when the app stops — a pattern worth copying whenever you own a long-lived connection.

---

That is all a provider needs to be: a priority, a register pass for the container, a boot pass for the world, and maybe a shutdown pass for teardown. Stack them in `bootstrap/providers.py`, and Arvel runs them in order so your application comes together predictably every time.
