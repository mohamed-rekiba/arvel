# Facades

Facades give you a clean, static-looking way to reach the services in arvel's [service
container](container.md). Instead of resolving a service by hand, you call a class method:

```python
from arvel import Cache

await Cache.put("greeting", "hello", ttl=60)
value = await Cache.get("greeting")
```

`Cache` isn't the cache itself — it's a **facade**: a thin proxy that forwards every call to the
real cache service resolved from the container under the hood. You get terse, readable call
sites without giving up the testability of dependency injection.

This page covers how that proxying works, the full list of facades, how they stay type-checked, how
to fake one in a test, and when to prefer dependency injection instead. Facades are part of the
**core** — nothing to install.

## How facades work

Every facade extends a base `Facade` and declares one thing — the container key it proxies (its
*accessor*). When you call `Cache.get(...)`, the facade resolves the `"cache"` service from the
current application's container and forwards the call to it:

```python
from arvel.support.facades import Facade

class Cache(Facade):
    @classmethod
    def accessor(cls) -> str:
        return "cache"
```

Because the root is resolved *dynamically* on every access, a facade always reflects the current
application — which is what makes faking it in tests (below) work transparently.

## Available facades

| Facade | Resolves | Facade | Resolves |
|--------|----------|--------|----------|
| `Config` | configuration | `Cache` | cache store |
| `Route` | the router | `DB` | database connections |
| `Auth` | authentication | `Gate` | authorization |
| `Storage` | file storage | `Queue` | job queue |
| `Event` | event dispatcher | `Mail` | mailer |
| `Log` | logger | `Hash` | password hashing |
| `Crypt` | encrypter | `Http` | HTTP client |
| `View` | view factory | `Lang` | translator |
| `Date` | date factory | `Validator` | validator factory |

Import them from the package root:

```python
from arvel import Cache, Auth, Storage, DB
```

## Typed by stubs

Facades resolve their methods dynamically, which a type checker can't see through on its own. So
arvel ships a generated type stub (`arvel/support/facades/__init__.pyi`) describing each facade's
methods — your editor autocompletes `Cache.get(...)` and mypy/pyright check the calls. The stub
is regenerated from the live services (`make stubs`), so it never drifts from the real API.

## Faking facades in tests

The big payoff: a facade can be swapped for a fake in a test, so you assert against behavior
without touching a real backend.

```python
from arvel import Cache

def test_dashboard_caches_stats():
    fake = Cache.fake()                 # swap in an in-memory implementation
    build_dashboard()
    assert fake.has("stats")            # the code under test populated the cache
```

`Cache.fake()` replaces the resolved root for the duration of the test; `Cache.swap(obj)` lets
you substitute any object you like. Roots reset on application boot.

## Facades vs. dependency injection

Facades are convenient, but they hide a dependency. In an **app service class**, prefer injecting
the underlying type so the dependency is explicit and the class is trivially unit-testable:

```python
from arvel.cache import CacheRepository

class ReportService:
    def __init__(self, cache: CacheRepository):   # explicit, autowired from the container
        self.cache = cache
```

A good rule of thumb: reach for a facade in routes, controllers, and quick scripts; inject the
contract in long-lived service classes. Both resolve from the same container, so they're never in
conflict.

## Common mistakes & gotchas

- **Using a facade with no app bootstrapped.** A facade resolves its service from the *current*
  application, so calling one before an app is created (or outside the app entirely) raises a
  "no application" error. In tests, build the app first.
- **Reaching for a facade where DI reads better.** Inside a service whose whole job is the cached
  thing, an injected contract states the dependency plainly and makes the unit test obvious — see
  above.
- **Forgetting to regenerate stubs.** Adding a facade (or changing a backing service's surface)
  means re-running the stub generator so the static types stay accurate — see *Typed by stubs*.

## See also

- [Service Container](container.md) — what facades resolve from.
- [Service Providers](providers.md) — where the services facades proxy are registered.
