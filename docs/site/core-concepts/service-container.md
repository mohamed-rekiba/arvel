# Service Container

<a name="introduction"></a>
## Introduction

The Arvel service container is a powerful tool for managing class dependencies and performing dependency injection. Dependency injection is a fancy phrase that essentially means this: class dependencies are "injected" into the class via the constructor instead of being constructed by the class itself.

Consider a `UserService` that needs a `Mailer`. Rather than building the mailer inside the service, you type-hint it in the constructor and let the container provide it:

```python
from arvel.container import Container


class Mailer: ...


class UserService:
    def __init__(self, mailer: Mailer) -> None:
        self.mailer = mailer


container = Container()
svc = container.make(UserService)   # Mailer is auto-wired
```

The `Application` owns a root container. In practice you interact with it through [service providers](service-providers.md), the [`dep()`](#resolving-in-routes-with-dep) helper in routes, and [facades](facades.md) — but understanding the container directly makes all of those clearer.

<a name="quick-start"></a>
### Quick start

Register bindings in a provider's `register()`, resolve in routes with `dep()`, or call `container.make()` / `await container.amake()` in services:

```python
# bootstrap/providers.py — register once
self.container.singleton(UserRepository)

# routes/api.py — inject per request
@Route.get("/users")
async def index(repo: UserRepository = Depends(dep(UserRepository))):
    return await repo.all()

# app/services/report_service.py — constructor injection
class ReportService:
    def __init__(self, repo: UserRepository) -> None:
        self.repo = repo
```

<a name="binding"></a>
## Binding

<a name="binding-basics"></a>
### Binding Basics

Almost all of your container bindings will be registered within [service providers](service-providers.md). Within a provider, you have access to the container via `self.container`. Register a binding with `bind`, passing the abstract type and a concrete type or factory:

```python
container.bind(Abstract, Concrete)
```

If the concrete is the same as the abstract, you may omit it:

```python
container.bind(UserService)
```

By default `bind` registers a **transient** binding — a new instance is created on every resolution.

<a name="binding-singletons"></a>
### Binding Singletons

The `singleton` method binds a type that should be resolved only once; the same instance is returned on every subsequent call:

```python
container.singleton(Mailer)
container.singleton(CacheStore, RedisCacheStore)
```

<a name="binding-scoped"></a>
### Binding Scoped

The `scoped` method binds a type that should be resolved once per [container scope](#container-scopes). Within a single scope the same instance is reused; a new scope gets a fresh instance:

```python
container.scoped(RequestContext)
```

<a name="binding-instances"></a>
### Binding Instances

You may bind an existing object instance into the container with `instance`. The given instance is returned on every resolution and takes priority over other bindings:

```python
container.instance(Clock, system_clock)
```

<a name="binding-if-not-bound"></a>
### Binding Only If Unbound

`bind_if`, `singleton_if`, and `scoped_if` register a binding only when nothing is already bound for that type. Use them to provide a default a downstream provider can override:

```python
container.singleton_if(CacheStore, ArrayCacheStore)   # no-op if already bound
```

<a name="binding-a-factory"></a>
### Binding a Factory

The concrete argument may be a callable factory instead of a class. The factory builds the instance when the type is resolved:

```python
container.singleton(HttpClient, lambda: HttpClient(timeout=30))
```

For async factories, register normally but resolve with [`amake`](#the-make-method) — resolving an async factory through the synchronous `make` raises `AsyncBindingError`.

```python
async def build_engine() -> AsyncEngine:
    return create_async_engine(database_url)

container.singleton(AsyncEngine, build_engine)
engine = await container.amake(AsyncEngine)
```

<a name="resolving"></a>
## Resolving

<a name="the-make-method"></a>
### The make Method

Use `make` to resolve a class instance out of the container. It takes the type you want, plus optional keyword overrides for individual constructor parameters — or for parameters a **factory binding** declares:

```python
svc = container.make(UserService)
svc = container.make(UserService, mailer=test_mailer)   # override one dependency

def make_widget(color: str = "default") -> Widget:
    return Widget(color)

container.bind(Widget, make_widget)
container.make(Widget, color="red")   # forwards to the factory's declared params
```

Overrides apply only to parameters the factory's signature actually declares; zero-arg factories ignore stray kwargs.

For bindings backed by an async factory, use `amake`. To resolve a class and call one of its methods with injected parameters, use `call` / `acall`:

```python
svc = await container.amake(AsyncService)
result = container.call(ReportBuilder, "build")
result = await container.acall(ReportBuilder, "build_async")
```

`amake` resolves async bindings **at any depth** — auto-wiring a class whose constructor needs an async-bound dependency (directly or transitively) works, as long as you start the resolution with `amake`/`acall`. The synchronous `make` still raises `AsyncBindingError` the moment it meets an async binding anywhere in the graph.

> [!WARNING]
> `call`/`acall` inject a method parameter only when its annotated type is already **bound** — unbound concrete types are not auto-wired the way constructor dependencies are (pass them via `overrides=`). And when a parameter's annotation arrives as a string (a locally-scoped type under [PEP 649](https://peps.python.org/pep-0649/)), the container matches it against bound types by class `__name__` alone, so two bound classes that share a name can resolve to the wrong one. Annotate `call` targets with module-level, uniquely-named types.

Check container state with `bound(abstract)` and `resolved(abstract)`.

Because `make`/`amake` accept the same key type as `bind`, you can resolve a bound interface or `Protocol` directly — `make(Mailer)` is type-checked as returning a `Mailer` with no `# type: ignore` at the call site.

> [!NOTE]
> `Application.make(...)` forwards to the root container's `make` and shares its signature: `app.make(Router)` is typed as returning a `Router`.

<a name="automatic-injection"></a>
### Automatic Injection

The container resolves constructor dependencies automatically from their type hints. A concrete class with type-hinted constructor parameters can be resolved without being explicitly bound — the container auto-wires it, recursively resolving each dependency:

```python
class OrderService:
    def __init__(self, mailer: Mailer, cache: CacheStore) -> None:
        ...


# No explicit binding needed; Mailer and CacheStore are resolved recursively.
service = container.make(OrderService)
```

> [!WARNING]
> Two cases can't be auto-wired and must be bound explicitly: abstract classes (you must bind a concrete implementation), and classes whose `__init__` is the default `object.__init__` with no declared dependencies the container can introspect. Bind those with `bind`/`singleton`.

<a name="resolution-order"></a>
### Resolution Order

When resolving a type, the container checks, in order:

1. A pre-registered **instance**.
2. A matching **contextual binding** (see below) for the current consumer.
3. A registered **binding** (`bind`/`singleton`/`scoped`), honoring its lifetime cache.
4. **Auto-wiring** of a concrete class via its `__init__` type hints.

<a name="contextual-binding"></a>
## Contextual Binding

Sometimes you may have two classes that utilize the same interface, but you wish to inject different implementations into each. Use the fluent `when`/`needs`/`give` API to give a specific consumer its own implementation:

```python
container.when(MarketingNotifier).needs(Mailer).give(SesMailer)
container.when(SystemNotifier).needs(Mailer).give(SmtpMailer)
```

`give` accepts a concrete type, an instance, or a factory.

<a name="tagging"></a>
## Tagging

Occasionally you may need to resolve all of a certain "category" of binding. Tag a set of bindings, then resolve them all at once with `tagged`:

```python
container.tag([SlackReporter, EmailReporter, SmsReporter], "reporters")

reporters = container.tagged("reporters")   # list of resolved instances
```

<a name="extending-bindings"></a>
## Extending Bindings

The `extend` method allows the modification of a resolved service. It takes a decorator that receives the instance (and the container) and returns the instance to use. Extending a singleton invalidates its cached instance so the decorator applies. A pre-built `instance()` is decorated in place. `bind()` and `extend()` also evict stale entries from singleton, instance, and scoped caches — including scoped instances cached in any **open child scope**. A decorator registered on a parent (or the root) container still applies when the type is resolved through a child scope:

```python
container.extend(Mailer, lambda mailer, c: LoggingMailer(mailer))
```

<a name="container-scopes"></a>
## Container Scopes

A scope is a child container that shares the parent's singleton and instance caches but maintains its own cache for [scoped](#binding-scoped) bindings. Open one with `scope` / `ascope`:

```python
with container.scope() as scoped:
    a = scoped.make(RequestContext)
    b = scoped.make(RequestContext)
    assert a is b               # same instance within the scope

async with container.ascope() as scoped:
    ctx = await scoped.amake(RequestContext)
```

When the scope exits, its scoped cache is cleared.

> [!NOTE]
> Scoped bindings only deduplicate within an explicit `scope()`/`ascope()` block today. Per-request child containers aren't wired into the HTTP path yet — the request scope currently points at the root container (see below).

<a name="resolving-in-routes-with-dep"></a>
## Resolving in Routes With dep()

FastAPI route handlers resolve container bindings through `dep()`, which adapts a binding into a FastAPI dependency:

```python
from fastapi import Depends
from arvel import Route, dep
from app.services.user_service import UserService


@Route.get("/users")
async def list_users(svc: UserService = Depends(dep(UserService))) -> list[dict]:
    return await svc.all()
```

`dep()` reads the container from `request.state.arvel_scope`, which the framework's scope middleware attaches automatically (mounted by `into_asgi()`).

> [!NOTE]
> `dep()` currently resolves against the **root** container; true per-request child scopes aren't wired into the HTTP path yet. If `dep()` is used without the scope middleware mounted, it raises a `RuntimeError`.

<a name="container-errors"></a>
## Container Errors

| Exception | Meaning |
|---|---|
| `BindingResolutionError` | The container can't build the requested type (unbound abstract, missing dependency, constructor mismatch). |
| `CircularDependencyError` | Dependencies form a cycle. |
| `AsyncBindingError` | Synchronous `make()` was used on a binding backed by an async factory — use `amake()`. |
