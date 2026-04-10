# Service Container

Dependency injection is not ceremony for its own sake — it keeps constructors honest, tests swap-friendly, and configuration centralized. Arvel’s container is small on purpose: **scoped lifetimes**, **interface-to-implementation binding**, and **constructor injection** that reads your type hints. If you have used Laravel’s service container, think of this as the same idea with explicit **scopes** and async-friendly resolution.

## Why Arvel uses a container

Framework code needs to compose mailers, caches, repositories, and auth services without hard-wiring concrete classes everywhere. Binding an interface (or an abstract contract type) in one place means the rest of your app asks for `MailContract`, not `SmtpMailer`. Tests can register fakes; production can read driver names from config — exactly the workflow Laravel developers expect, expressed with Python typing.

## ContainerBuilder vs Container

During the **register** phase of a service provider you receive a **`ContainerBuilder`**. It only collects bindings — it does not resolve anything yet.

After all providers finish registering, the framework calls `build()` and hands you an immutable binding map wrapped in a **`Container`** rooted at **APP** scope. That is the object you resolve from at runtime (often indirectly through request scope — more below).

```python
from arvel.foundation.container import ContainerBuilder, Scope

async def register(self, container: ContainerBuilder) -> None:
    container.provide(NotifierProtocol, EmailNotifier, scope=Scope.REQUEST)
    container.provide_factory(
        AuditLogger,
        lambda: AuditLogger(sink=sys.stdout),
        scope=Scope.APP,
    )
```

## Binding services

Arvel uses three registration styles (Laravel’s `bind` / `singleton` map cleanly to these):

| Idea | Arvel API | Typical scope |
|------|-----------|----------------|
| Bind interface → concrete class | `provide(interface, concrete, scope=...)` | `REQUEST` default |
| Bind interface → factory callable | `provide_factory(interface, factory, scope=...)` | Often `APP` for expensive clients |
| Bind to a ready-made value | `provide_value(interface, value, scope=...)` | Usually `APP` for settings snapshots |

**APP** scope behaves like a singleton for the process lifetime. **REQUEST** scope creates (or reuses) instances per HTTP request when you enter a child container. **SESSION** scope is reserved for values that should follow a user session across requests — resolution chains through the parent when a request-scoped container does not own the binding.

```python
from arvel.foundation.container import ContainerBuilder, Scope

class Settings: ...

def build_container() -> None:
    builder = ContainerBuilder()
    builder.provide_value(AppConfig, Settings(), scope=Scope.APP)
    builder.provide(UserRepository, SqlUserRepository, scope=Scope.REQUEST)
    root = builder.build()
```

## Resolving services

The runtime API is **`await container.resolve(SomeType)`** — there is no separate `make` name, but the intent is identical: materialize `SomeType` according to its binding and recursively satisfy `__init__` parameters that have type hints.

```python
async def handle(self) -> None:
    mailer = await self._container.resolve(MailContract)
    await mailer.send("hello@example.com", "Ping")
```

If a class is registered and its constructor lists typed dependencies, the container resolves each parameter automatically. Optional parameters with defaults are left alone when the hint cannot be resolved.

After boot, you can also pin a pre-built instance — useful when `boot()` wires something that depends on other resolved services:

```python
await app.container.instance(CacheContract, shared_cache)
```

## Scopes in practice

- **APP** — One logical instance for the whole application process (subject to how you bind factories). Infrastructure drivers (Redis clients, mailers) usually live here.
- **REQUEST** — A fresh child container is created per HTTP request (`RequestScopeMiddleware` calls `enter_scope(Scope.REQUEST)`). Route handlers and controllers resolve against this child so repositories and sessions do not leak across users.
- **SESSION** — Bindings that should survive for a session attach to the parent chain; the request container delegates upward when needed.

```python
from arvel.foundation.container import Scope

child = await app_container.enter_scope(Scope.REQUEST)
try:
    repo = await child.resolve(OrderRepository)
finally:
    await child.close()
```

In real apps you rarely write that loop — `RequestContainerMiddleware` installs the scoped container on each request’s ASGI scope for you.

## The `Inject` helper for controllers

`Inject` bridges FastAPI’s `Depends()` machinery to the Arvel container. Use it as a **default value** on controller action parameters so static analysis still sees the true type.

```python
from arvel.http.controller import Inject
from arvel.security.contracts import HasherContract

class AuthController(BaseController):
    @route.post("/login")
    async def login(
        self,
        payload: LoginRequest,
        hasher: HasherContract = Inject(HasherContract),
    ) -> TokenResponse:
        ...
```

Behind the scenes, FastAPI treats `Inject(T)` as a dependency that pulls `T` from `request.state.container`, which `RequestContainerMiddleware` populates for each request.

---

That is the container story: declare in `ContainerBuilder`, resolve from `Container`, scope by lifetime, and let `Inject` keep controller signatures tidy. Everything else in the framework builds on those four moves.
