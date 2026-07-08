# Service Container

The container is how arvel wires your app together. As an app grows, "construct the thing that
needs the other thing that needs the database connection" becomes a tangle of manual wiring — the
container untangles it. It resolves classes and their dependencies automatically, so a controller
can just *declare* what it needs and the container constructs the whole graph; no manual `new`
chains, no global singletons you pass around by hand.

This page covers resolving and binding services, controlling their lifetimes, contextual and tagged
bindings, the resolve/extend hooks that let packages customize the graph, and calling functions with
their arguments injected. The container is part of the **core** — nothing to install.

## Resolving with autowiring

If a class's dependencies are themselves resolvable, the container builds the whole graph for
you — this is **autowiring**:

```python
class Mailer: ...
class WelcomeService:
    def __init__(self, mailer: Mailer):     # the container sees this dependency
        self.mailer = mailer

service = app.make(WelcomeService)           # Mailer is constructed and injected
```

You rarely call `make` yourself in app code — controllers and listeners are resolved *through*
the container, so their constructor dependencies arrive injected.

## Binding

Tell the container how to build an abstract type — usually to bind an **interface to an
implementation**:

```python
app.bind(Clock, SystemClock)                 # make(Clock) -> a new SystemClock each time
app.bind("report", lambda c: Report(c.make(Db)))   # a factory closure
```

`make` runs the factory (or constructs the class), resolving any nested dependencies.

## Lifetimes

| Method | Lifetime |
|--------|----------|
| `bind` | a **new** instance every `make` |
| `singleton` | **one** shared instance for the app's lifetime |
| `scoped` | one instance **per scope** (e.g. per request), reset between scopes |
| `instance` | register an **already-built** object |

```python
app.singleton(Db, lambda c: Db.connect(env("DB_URL")))   # shared pool
app.scoped(RequestContext, RequestContext)                # fresh per request
app.instance("config", loaded_config)                     # pre-built
```

## Aliases

Give a binding a short string name:

```python
app.alias("db", Db)
app.make("db")          # same as app.make(Db)
```

## Contextual bindings

Two consumers can need the *same* interface resolved *differently*. `when…needs…give`
expresses that:

```python
(app.when(PhotoController)
    .needs(Filesystem)
    .give(lambda c: c.make(FilesystemManager).disk("s3")))

(app.when(InvoiceController)
    .needs(Filesystem)
    .give(lambda c: c.make(FilesystemManager).disk("local")))
```

## Extending a resolved service

Wrap or decorate a binding after it's built — useful for adding behavior to a service a package
registered:

```python
app.extend(Mailer, lambda mailer, c: LoggingMailer(mailer))
```

The closure runs on the next resolve. If the service is a **singleton that's already been
resolved**, `extend` applies the closure to the existing instance immediately — so extending a
service late still takes effect everywhere it's already been injected.

## Resolving hooks

Run a callback every time a type is resolved — handy for configuring every instance a package
hands out (e.g. tagging every logger). `resolving` fires as the object is built; `after_resolving`
fires right after:

```python
app.resolving(Logger, lambda logger, c: logger.add_context(app="arvel"))
app.after_resolving(Logger, lambda logger, c: logger.flush_buffer())
```

Both fire for every resolve — transient, shared, and the first build of a `scoped` binding.

## Calling with injection

`call` invokes a function and injects its parameters from the container — how jobs, listeners,
and controller methods get their dependencies:

```python
async def handle(self, transcoder: Transcoder):    # resolved + injected by the worker
    await transcoder.process(self.podcast)
```

To override how a specific method is resolved, register it with `bind_method` — `call` then runs
your closure instead of the method:

```python
app.bind_method([ReportJob, "handle"], lambda job, c: job.handle(c.make(Exporter)))
```

## Putting it together

The pieces above compose into a pattern you'll use constantly: bind an interface once in a
provider, depend on that interface everywhere else, and never wire the graph by hand. Say a report
endpoint needs a database connection and a mailer:

```python
# in a provider's register()
app.singleton(Db, lambda c: Db.connect(env("DB_URL")))     # one shared pool
app.bind(Mailer, SmtpMailer)                                 # interface → implementation

# an app service that declares what it needs — no `make`, no globals
class ReportService:
    def __init__(self, db: Db, mailer: Mailer):
        self.db = db
        self.mailer = mailer

# a handler that depends on the service
async def send_report(request, reports: ReportService):     # resolved through the container
    await reports.mailer.send(await reports.db.fetch_all(...))
```

When the request arrives, the container resolves `ReportService`, sees it needs a `Db` and a
`Mailer`, hands it the shared `Db` singleton and a freshly-built `SmtpMailer`, and injects the
finished service into the handler. You wrote three declarations; the container built the graph.
Swap `SmtpMailer` for a fake in a test by rebinding `Mailer` — nothing else changes.

## What autowiring can resolve

`make` reads the constructor's type hints and injects each dependency it can build. The rules:

- **Class-typed params** are resolved recursively (`make`-d).
- **Keyword-only params** (`def __init__(self, *, cache): …`) are honored — they're passed by
  keyword, never positionally.
- **Non-injectable annotations** — `typing.Any`, primitives (`int`/`str`/…), generics like
  `list[str]`, or an unresolvable forward reference — are **not** built. If the param has a default
  or is `Optional`, that default/`None` is used; otherwise `make` raises a clear
  `BindingResolutionError` (never a raw `TypeError`/`NameError`). So a service with a
  `cache: Any = None` or `dep: "Forward" = None` param autowires cleanly.

This is why the framework's own middleware (e.g. `StartSession`, `ThrottleRequests` — both with
keyword-only, `Any`-typed ctor params) can be built by the container per request.

## Common mistakes & gotchas

- **`singleton` holding request state.** A singleton lives for the whole process — don't store
  per-request data on it (use `scoped` for that), or requests will see each other's state.
- **Binding a concrete you could autowire.** If a class has no interface and resolvable
  dependencies, you don't need to bind it at all — `make` autowires it. Bind only to map an
  interface, supply config, or control the lifetime.
- **Circular dependencies.** A → B → A can't be constructed; the container raises rather than
  looping forever. Break the cycle (often with a lazy lookup or an event).

## How it works

The container keeps registries for bindings, shared singletons, per-scope instances, aliases,
and contextual overrides. `make` resolves an alias, checks for a cached singleton/scoped
instance, applies any contextual override for the current build target, then constructs —
reading the target's constructor type hints and recursively `make`-ing each dependency. A build
stack tracks the resolution chain so contextual bindings know who's asking and circular
dependencies are detected.

## See also

- [Service Providers](providers.md) — where you register bindings at boot.
- [Queues & Jobs](queues.md) · [Events](events.md) — both inject via `call`.
