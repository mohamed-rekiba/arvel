# Service Container

Arvel ships a small, explicit dependency-injection container — `arvel.Container`. Everything the framework does at runtime resolves through it, including the facades.

## What the container actually does

The container holds three kinds of bindings:

| Binding | Created… | Lifetime |
|---|---|---|
| `bind(T, factory)` | every time you `resolve(T)` | per-resolve |
| `singleton(T, factory)` | on first `resolve(T)` | for the lifetime of the container |
| `instance(T, obj)` | never (you provide the object) | for the lifetime of the container |

When `resolve(T)` is called, the container introspects `T`'s `__init__` signature and tries to fill each parameter from its own bindings. If a parameter has a default value, the default wins when no binding exists.

```python
from arvel import Application, Container


class Mailer:
    def send(self, to: str) -> None: ...


container = Container()
container.singleton(Mailer)

mailer = container.resolve(Mailer)  # same instance every call
```

## Binding interfaces to implementations

You can bind an abstract type to a concrete factory:

```python
from typing import Protocol

class Clock(Protocol):
    def now(self) -> str: ...


class SystemClock:
    def now(self) -> str:
        from datetime import UTC, datetime
        return datetime.now(UTC).isoformat()


container.singleton(Clock, SystemClock)

clock = container.resolve(Clock)  # → SystemClock instance
```

In tests, swap the binding:

```python
class FrozenClock:
    def now(self) -> str:
        return "2026-01-01T00:00:00+00:00"


container.instance(Clock, FrozenClock())
```

## `arvel.dep` and FastAPI

`arvel.dep(T)` is a small adapter that lets you ask the container for `T` from inside a FastAPI handler. It's implemented on top of FastAPI's `Depends`, so it composes with everything FastAPI knows about.

```python
from arvel import Route, dep


@Route.get("/orders")
async def list_orders(mailer: Mailer = dep(Mailer)) -> list[dict[str, str]]:
    ...
```

`dep` resolves against the container stashed on `request.app.state.arvel_container`, which `Application.into_asgi()` sets for you.

## Service location via facades

Most users don't reach for `container.resolve(...)` directly — facades are the friendlier interface:

```python
from arvel.facades import Cache, DB, Mail


await Cache.put("key", "value", ttl=60)
posts = await DB.table("posts").get()
await Mail.to("user@example.com").send(WelcomeMail())
```

Each facade resolves its underlying service from the container lazily on first access. See [Facades](facades.md) for how they work.

## Scoped bindings

`scoped()` is like `singleton()` but the instance lives only for the duration of a **container scope**, not the whole application lifetime. A new scope creates a child container that resets scoped instances when it exits — useful for per-request caches or unit-of-work patterns:

```python
container.scoped(UnitOfWork)

async def handle_request() -> None:
    async with container.ascope() as scoped:
        uow1 = scoped.make(UnitOfWork)
        uow2 = scoped.make(UnitOfWork)
        assert uow1 is uow2        # same instance within the scope
    # scope exited — UnitOfWork instance is discarded
```

The binding lifetimes in full:

| Method | Instance lifetime |
|---|---|
| `bind` | per `make()` call |
| `singleton` | container lifetime |
| `scoped` | current scope lifetime |
| `instance` | container lifetime (pre-built) |

## Contextual binding

When two consumers need the *same abstract* but *different implementations*, use `when().needs().give()`:

```python
from arvel import Container


class FileLogger:
    ...

class DatabaseLogger:
    ...

class Logger(Protocol):
    ...


container.when(ReportService).needs(Logger).give(FileLogger)
container.when(BillingService).needs(Logger).give(DatabaseLogger)

report  = container.make(ReportService)   # gets FileLogger
billing = container.make(BillingService)  # gets DatabaseLogger
```

`give()` accepts a class, a factory callable, or a pre-built instance.

## Aliases

Bind a string name to a type so service-location code doesn't need to import the concrete class:

```python
container.alias(CacheStore, "cache")

# Resolved elsewhere by string name — useful inside plugins or shell commands:
cache = container.make(container._aliases["cache"])
```

## Tagging

Group related bindings under a label, then resolve them all at once:

```python
container.singleton(CsvExporter)
container.singleton(XlsxExporter)
container.singleton(PdfExporter)

container.tag([CsvExporter, XlsxExporter, PdfExporter], "exporters")

# Elsewhere — resolve every exporter without knowing the concrete list:
exporters = container.tagged("exporters")   # [CsvExporter(), XlsxExporter(), PdfExporter()]

for exporter in exporters:
    await exporter.export(report)
```

## Extending resolved instances

`extend()` lets you decorate an already-resolved singleton — add logging, wrap in a proxy, set a field — without altering the original binding:

```python
def add_prefix(mailer: Mailer, _container: Container) -> Mailer:
    mailer.subject_prefix = "[Arvel] "
    return mailer

container.extend(Mailer, add_prefix)
```

If the singleton is already cached when `extend()` is called, the cache is invalidated so the decorator runs on the next `make()`.

## Async resolution

When the factory for a binding is itself a coroutine (or the constructor has an `async def __init__`), use `amake()` instead of `make()`:

```python
async def build_db_pool(c: Container) -> DatabasePool:
    return await DatabasePool.connect(c.make(DatabaseConfig))

container.singleton(DatabasePool, build_db_pool)

pool = await container.amake(DatabasePool)
```

## Introspection

```python
container.bound(Mailer)    # True if a binding or instance is registered
container.resolved(Mailer) # True if the singleton/scoped cache has a live instance
```

Useful in service providers and tests to guard against double-registration.

## Closure-scope auto-wiring (test-only)

When you decorate a handler with `@Route.get(...)`, Arvel needs to resolve its type annotations at registration time — for example, to detect `FormRequest[T]` parameters and rewrite the signature.

In production code, all types are top-level: imported from your modules. They resolve cleanly via `typing.get_type_hints()`.

In tests, though, you often define throw-away types inside the test function:

```python
def test_some_handler() -> None:
    class StoreUser(FormRequest[dict[str, str]]):
        name: str

    @Route.post("/users")
    async def create(form: StoreUser) -> dict[str, str]:
        return {"name": form.name}
```

That `StoreUser` only exists in the local scope of `test_some_handler`. Standard `typing.get_type_hints()` cannot see it, because it walks module-level namespaces.

Arvel works around this in `_resolve_annotations()` by capturing `caller_locals = sys._getframe(...).f_locals` when the decorator runs, and merging it into the namespace used for type resolution. This is what we call **closure-scope auto-wiring**.

### Why this is test-only

- **Production handlers should not depend on enclosing scope.** They are typically module-level functions whose parameter types are imported at the top of the file. The standard resolution path covers them perfectly.
- **`sys._getframe()` is intentionally CPython-specific** and slow. It's fine for one-time route registration in tests; it would be wasteful in tight inner loops.
- **Scope-captured types break refactoring.** If someone extracts a closure into a separate function later, the type is no longer in scope. Production code should use module-level definitions.

Treat closure-scope auto-wiring as a **test ergonomics feature** that lets you keep your tests self-contained. If you ever find yourself relying on it in production code, hoist the type to module scope.

## Where to next?

- [Service Providers](providers.md) — where you actually register your bindings.
- [Facades](facades.md) — how facades resolve under the hood.
- [Request Lifecycle](lifecycle.md) — when the container is built.
