# Facades

A facade is a short, static-looking way to reach a service in the [container](container.md). Instead
of resolving the cache by hand and calling it, you write:

```python
from arvel import Cache

await Cache.put("greeting", "hello", ttl=60)
value = await Cache.get("greeting")
```

`Cache` here is not the cache. It's a **facade** — a thin proxy whose every call is forwarded to the
real cache service, resolved from the current application's container the moment you call it. You get
a terse, readable call site without the thing you'd normally trade for it: because the facade resolves
through the container, you keep the testability of dependency injection, and you can swap the backing
service for a fake in a test without touching the calling code.

This page covers how the proxying works, the full set of facades, how they stay type-checked, how to
fake one in a test, and when to inject the underlying service instead. Facades are part of the
**core** — nothing to install.

## How a facade works

Every facade extends a base `Facade` and declares exactly one thing: the container key it stands in
for, its **accessor**. When you call a method on the facade, it resolves that key from the current
application and forwards the call:

```python
from arvel.support.facades import Facade

class Cache(Facade):
    @classmethod
    def accessor(cls) -> str:
        return "cache"      # Cache.get(...) → app.make("cache").get(...)
```

The key word is *current*. The facade doesn't hold a reference to a cache — it looks the service up
on every access, against whatever application is bootstrapped right now. That indirection costs a
dictionary lookup and buys you two things: a facade always reflects the live application, and swapping
the backing service (a fake, in a test) is transparent to every call site.

## Available facades

Import any of them straight from the package root — `from arvel import Cache, Auth, DB`:

| Facade | Resolves to | Facade | Resolves to |
|--------|-------------|--------|-------------|
| `Config` | configuration store | `Cache` | cache repository |
| `Route` | the router | `DB` | database connections |
| `Auth` | authentication | `Gate` | authorization |
| `Storage` | file storage | `Queue` | job queue |
| `Event` | event dispatcher | `Mail` | mailer |
| `Log` | logger | `Hash` | password hashing |
| `Crypt` | encrypter | `Http` | HTTP client |
| `View` | view factory | `Lang` | translator |
| `Date` | date factory | `Validator` | validator factory |
| `Redis` | Redis connection | `Schedule` | task scheduler |
| `RateLimiter` | rate limiter | | |

Each proxies one container service — `Cache` the cache repository, `Queue` the job queue, and so on.
The method surface you call on a facade is exactly the surface of the service behind it, which is why
each facade's methods are documented on that feature's own page ([Cache](cache.md),
[Queues](queues.md), …) rather than duplicated here.

## Typed by stubs

A facade resolves its methods dynamically, which a type checker can't follow on its own — to mypy,
`Cache.get` is just an attribute access on a class that doesn't define `get`. So arvel ships a
generated **type stub** (`arvel/support/facades/__init__.pyi`) that declares each facade's methods
with their real signatures. Your editor autocompletes `Cache.get(...)`, and mypy and pyright check
the call, even though the method only exists at runtime.

The stub is generated *from the live services* (`make stubs`), not written by hand — so it can't
drift from the real API. Add a method to the cache repository, regenerate, and the facade's type
picks it up. This is the detail that makes facades safe in a typed codebase: the ergonomics of a
dynamic proxy with the checking of a real method call.

## Faking a facade in a test

Here's the payoff that a bare `app.make("cache")` wouldn't give you. Because the facade resolves its
service every time, a test can swap that service for an in-memory fake and then assert against it — no
real backend, no network, no cleanup:

```python
from arvel import Cache

def test_dashboard_caches_stats():
    fake = Cache.fake()          # swap the resolved "cache" for an in-memory double
    build_dashboard()            # code under test calls Cache.put(...) as normal
    assert fake.has("stats")     # assert it populated the cache
```

`Cache.fake()` replaces the backing service for the duration of the test and hands you the fake to
assert on. When you need to substitute something more specific, `Cache.swap(obj)` puts any object you
like behind the facade. Resolved roots reset on application boot, so tests don't leak into each other.

## Facades vs. dependency injection

A facade is convenient precisely because it hides a dependency — and that's also its cost. In a
long-lived **service class**, a hidden dependency is a liability: the class's constructor no longer
tells you what it needs, and the unit test has to reach for the facade's fake instead of just passing
a double. There, inject the underlying contract:

```python
from arvel.cache import CacheRepository

class ReportService:
    def __init__(self, cache: CacheRepository):   # explicit, autowired from the container
        self.cache = cache
```

Now the dependency is in the signature, and the test constructs `ReportService(FakeCache())` with no
facade machinery at all.

The rule of thumb: **reach for a facade in routes, controllers, and quick scripts** — code that's
short-lived and read top-to-bottom, where the terseness wins and the hidden dependency doesn't hurt.
**Inject the contract in service classes** — code that lives a long time and deserves an honest
constructor. Both resolve from the same container, so mixing them is never a conflict; it's just
picking the right tool for the layer.

## Common mistakes & gotchas

- **Using a facade before an app exists.** A facade resolves against the *current* application, so
  calling one before an app is bootstrapped — or outside the app entirely — raises a "no application"
  error. In a test, build the app first.
- **Reaching for a facade where injection reads better.** If a class's whole job is the cached (or
  queued, or mailed) thing, an injected contract states that plainly and makes the unit test obvious.
- **Forgetting to regenerate stubs.** Add a facade, or change a backing service's surface, and rerun
  the stub generator — otherwise the static types quietly lag the runtime.

## See also

- [Service Container](container.md) — what a facade resolves from, and the injection alternative.
- [Service Providers](providers.md) — where the services facades proxy get registered.
- [Testing](testing.md) — faking facades and services in the test harness.
