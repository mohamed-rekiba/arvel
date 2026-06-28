# Architecture Concepts

arvel is built around *developer experience* first — but the kind that survives growth, not just a
clean hello-world. Three principles keep the framework honest as it scales: it stays **light**, it
leans on **best-in-class engines** rather than reinventing them, and it's **type-safe** with those
guarantees enforced mechanically. This page walks through each, then the **application lifecycle**
that ties them together, and what state to **share** once you run more than one instance.

## 1. Light by default

Importing `arvel` must pull in **zero** heavy third-party libraries. The public surface
is resolved lazily through a module-level `__getattr__` (PEP 562):

```python
import arvel            # imports nothing heavy — no Litestar, SQLAlchemy, taskiq, …
from arvel import Model # imports arvel.database (and SQLAlchemy) only now
```

Every capability module lazy-imports its engine *inside* the function that needs it, so
the T0 CLI and cold-start stay instant. This is verified mechanically: a startup test
spawns a fresh interpreter and asserts no heavy module is loaded after `import arvel`.

## 2. Best-in-class engines, never reinvented

Each capability is backed by a **mandated** library — and a *stack-fidelity* test suite
fails the build if a capability is ever quietly reimplemented in stdlib:

| Capability | Engine | Capability | Engine |
|---|---|---|---|
| HTTP / OpenAPI | Litestar | Cache | cashews |
| ORM | SQLAlchemy Core | Storage | fsspec |
| Validation | msgspec | Mail | aiosmtplib |
| Dates | whenever | Notifications | apprise |
| Console | Typer | Templates | Jinja2 |
| Localization | Babel | Queue | taskiq |
| Hash / Crypt | pwdlib / cryptography | Images / Video | Pillow / av |

*Lazy-import ≠ reimplement.* arvel adds the ergonomic seam; the engine does the work.

## 3. Type-safe & mechanically enforced

- **Strict typing** under both `mypy` and `pyright`, PEP 695 generics throughout.
- **Architecture rules** enforced by `import-linter`: the kernel stays isolated, and the
  light core may never import a heavy library — even transitively.
- **One DI container** wires it together; services resolve through contracts, and
  **facades** (`Cache`, `Queue`, `Mail`, `Gate`, …) are static-looking proxies over them.

## The application lifecycle

**Serving.** Your ASGI entry point is just `Application().as_asgi()`. That call runs the
**synchronous** bootstrap (load `.env` + `config/*.py`, configure logging, register providers — so
the router and bindings exist) and compiles the routes onto Litestar, then attaches a **lifespan** so
the **async** `boot()` runs on ASGI startup and `terminate()` on shutdown:

```python
# asgi.py — what your server (granian/uvicorn) imports
from arvel import Application
asgi_app = Application().as_asgi()   # sync bootstrap now; boot()/terminate() on startup/shutdown
```

The split exists because the ASGI app must be built **with its routes already in place** (synchronous
provider `register`), while a provider's `boot()` may be `async` and belongs in the server's lifespan.
If `boot()` fails, a partial boot is still `terminate()`d so half-opened resources are released.

For a worker or a one-shot (no ASGI server), drive the same sequence with the `lifespan` async context
manager (`async with lifespan(app): ...`), or call `await app.boot()` / `await app.terminate()`
yourself in tests.

Service providers register bindings and boot in dependency order; the container
autowires constructor dependencies; and a request flows through the two-tier middleware
pipeline before reaching your handler.

## Running multiple instances (shared state)

A few subsystems keep state **in-process by default** — fine for one instance, but in-process
state is lost on restart and **not shared** across replicas. Before you scale horizontally, point
each of these at a shared backend (Redis is the usual one):

| Subsystem | Default (single instance) | Shared / persistent backend |
|-----------|---------------------------|-----------------------------|
| **Cache** | `array` (in-process) | `redis` driver — set `cache.default = "redis"` + `cache.url` (`[redis]` extra) |
| **Session** | in-process dict | cache-backed: `StartSession(cache=cache())` over Redis |
| **Throttle** | in-process dict | cache-backed: `ThrottleRequests(cache=cache())` — one shared counter (Redis `INCR`) |
| **Queue** | `InMemoryBroker` | taskiq **Redis** broker (`[queue]` pulls `taskiq-redis`); jobs survive restarts + fan out to workers |
| **Maintenance flag** | stored in the **default cache** (so it follows `cache.default`) | use the `redis` cache so `arvel down` reaches every instance + survives restarts (with `array` it's per-process) |

```python
from arvel.support import cache
from arvel.http.middleware import ThrottleRequests, StartSession

# distributed limiting + sessions: every instance shares one Redis-backed store
api.append_to_group("api", ThrottleRequests(max_attempts=60, cache=cache()))
web.append_to_group("web", StartSession(cache=cache()))
```

Not every "global" is a scaling risk: the **model registry** (class-name → model, for polymorphic
relations) is *type metadata*, rebuilt deterministically on import — it's read-only and identical
on every instance, so it needs no shared store.

## See also

- [Packaging & Extras](packaging.md) — how "light by default" is built and enforced.
- [Service Container](container.md) · [Service Providers](providers.md) — the wiring and bootstrap
  the lifecycle runs.
- [Cache](cache.md) · [Queues & Jobs](queues.md) — the shared backends to configure before scaling
  out.
