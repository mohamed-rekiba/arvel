# Architecture Concepts

Before you build with arvel, it's worth ten minutes to understand how the pieces fit — not the
internals, but the handful of ideas the whole framework is arranged around. Get these and the rest of
the documentation reads as obvious; skip them and you'll keep meeting machinery that seems to appear
from nowhere.

arvel is built for *developer experience* — but the durable kind that holds up as an app grows past
hello-world, not the kind that photographs well in a README. Three commitments keep it honest: it
stays **light**, it leans on **best-in-class engines** instead of reinventing them, and it's
**type-safe**, with all three enforced mechanically rather than left to discipline. This page walks
through each, then the **lifecycle** that turns your code into a running app, and finally the shared
state to think about once you run more than one instance.

## Light by default

Importing `arvel` pulls in **zero** heavy third-party libraries. The public surface resolves lazily
through a module-level `__getattr__` (PEP 562), so you only pay for a subsystem when you reach for it:

```python
import arvel            # imports nothing heavy — no Litestar, SQLAlchemy, taskiq, …
from arvel import Model # NOW arvel.database (and SQLAlchemy) loads — because you asked for it
```

Every capability module lazy-imports its engine *inside* the function that needs it, so cold starts
and the CLI's fast paths stay instant. And this isn't a convention that quietly rots: a startup test
spawns a fresh interpreter and asserts that nothing heavy is loaded after `import arvel`. The weight is
opt-in, and the framework fails its own build if that ever stops being true. (The full mechanism —
extras, the import-linter contracts — is in [Packaging & Extras](packaging.md).)

## Best-in-class engines, never reinvented

arvel doesn't write its own ORM, HTTP server, or template engine. Each capability is backed by a
**mandated** library, and a stack-fidelity test suite fails the build if a capability is ever quietly
reimplemented in stdlib:

| Capability | Engine | Capability | Engine |
|---|---|---|---|
| HTTP / OpenAPI | Litestar | Cache | cashews |
| ORM | SQLAlchemy Core | Storage | fsspec |
| Validation | msgspec | Mail | aiosmtplib |
| Dates | whenever | Notifications | apprise |
| Console | Typer | Templates | Jinja2 |
| Localization | Babel | Queue | taskiq |
| Hash / Crypt | pwdlib / cryptography | Images / Video | Pillow / av |

What arvel adds is the *ergonomic seam* — a small, consistent, Pythonic surface over each engine — not
a reimplementation of it. When you write `Model.where(...)`, SQLAlchemy Core does the SQL; arvel just
gives you a nicer way to ask. The upshot: you get familiar, battle-tested behavior and can drop to the
raw engine whenever you need to, without fighting an abstraction that pretends the engine isn't there.

## Type-safe, mechanically enforced

- **Strict typing** under both `mypy` and `pyright`, with PEP 695 generics throughout.
- **Architecture rules** enforced by `import-linter`: the kernel stays isolated, the light core may
  never import a heavy library (even transitively), and the module dependency graph stays acyclic.
- **One container** wires everything, services resolve through contracts, and **facades** are
  static-looking proxies over them — with generated stubs so the dynamic proxying stays type-checked.

The theme across all three commitments: the guarantees are *tested*, not trusted. That's what lets a
one-person team move fast without the framework silently drifting out from under them.

## The application lifecycle

Here's what actually happens when your app starts. Your ASGI entry point is a single call:

```python
# asgi.py — what your server (granian/uvicorn) imports
from arvel import Application
asgi_app = Application().as_asgi()   # sync bootstrap now; boot()/terminate() on startup & shutdown
```

`as_asgi()` runs the **synchronous bootstrap** immediately — load `.env` and `config/*.py`, configure
logging, run every provider's `register` so the container is populated, and compile the routes onto
Litestar. Then it attaches a **lifespan** so the **async** work runs at the right time: each
provider's `boot()` on ASGI startup, and `terminate()` on shutdown.

That split isn't arbitrary. The ASGI app has to be built *with its routes already in place* — which is
synchronous provider `register` — while a provider's `boot()` may be `async` (opening a pool, warming a
cache) and belongs in the server's lifespan. If `boot()` fails partway, the app still `terminate()`s
what did come up, so half-opened resources are released rather than leaked.

Outside an ASGI server — a worker, a one-shot script, a test — you drive the same sequence yourself
with the `lifespan` async context manager (`async with lifespan(app): ...`) or by calling
`await app.boot()` / `await app.terminate()` directly.

Three subsystems do the heavy lifting inside that lifecycle, and they each get their own page:

- The **[service container](container.md)** constructs your objects and injects their dependencies.
- **[Service Providers](providers.md)** register and boot every feature, yours and the framework's.
- **[Facades](facades.md)** give you terse, testable access to the services the container holds.

Read those three next, in that order — they're the working parts of everything above.

## Running multiple instances

A few subsystems keep state **in-process by default**. That's exactly right for a single instance, but
in-process state is lost on restart and isn't shared across replicas — so before you scale
horizontally, point each of these at a shared backend (Redis is the usual choice):

| Subsystem | Default (single instance) | Shared / persistent backend |
|-----------|---------------------------|-----------------------------|
| **Cache** | `array` (in-process) | `redis` driver — set `cache.default = "redis"` + `cache.url` (`[redis]` extra) |
| **Session** | in-process dict | cache-backed: `StartSession(cache=cache())` over Redis |
| **Throttle** | in-process dict | cache-backed: `ThrottleRequests(cache=cache())` — one shared counter (Redis `INCR`) |
| **Queue** | `InMemoryBroker` | taskiq **Redis** broker (`[queue]` pulls `taskiq-redis`); jobs survive restarts + fan out to workers |
| **Maintenance flag** | stored in the **default cache** (follows `cache.default`) | use the `redis` cache so `arvel down` reaches every instance + survives restarts |

```python
from arvel.support import cache
from arvel.http.middleware import ThrottleRequests, StartSession

# distributed limiting + sessions: every instance shares one Redis-backed store
api.append_to_group("api", ThrottleRequests(max_attempts=60, cache=cache()))
web.append_to_group("web", StartSession(cache=cache()))
```

Not every process-global is a scaling hazard, though. The **model registry** (class-name → model, for
polymorphic relations) is *type metadata* — rebuilt deterministically on import, read-only, and
identical on every instance — so it needs no shared store. The rule of thumb: shared *data* needs a
shared backend; shared *code-derived metadata* doesn't.

## See also

- [Service Container](container.md) · [Service Providers](providers.md) · [Facades](facades.md) — the
  three working parts of the lifecycle above.
- [Packaging & Extras](packaging.md) — how "light by default" is built and enforced in CI.
- [Cache](cache.md) · [Queues & Jobs](queues.md) — the shared backends to configure before scaling out.
