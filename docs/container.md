# Service Container

The service container is a powerful tool for managing class dependencies and performing dependency
injection. As an app grows, "construct the thing that needs the other thing that needs the database
connection" becomes a tangle of manual wiring — the container untangles it. It resolves classes and
their dependencies automatically, so a controller can just *declare* what it needs; no manual `new`
chains, no global singletons passed around by hand. The container is part of the **core** — nothing to
install.

## Binding

### Simple bindings

Tell the container how to build a type with `bind` — a class, or a factory closure. `make` runs the
factory (or constructs the class), resolving any nested dependencies:

```python
app.bind(Clock, SystemClock)                       # make(Clock) -> a new SystemClock each time
app.bind("report", lambda c: Report(c.make(Db)))   # a factory closure
```

### Binding a singleton

`singleton` binds a type resolved **once** — the same instance is returned on every subsequent `make`:

```python
app.singleton(Db, lambda c: Db.connect(env("DB_URL")))   # one shared pool
```

### Binding scoped

`scoped` binds a type resolved once **per scope** (e.g. per request), reset between scopes:

```python
app.scoped(RequestContext, RequestContext)               # fresh per request
```

### Binding instances

Register an already-built object with `instance`:

```python
app.instance("config", loaded_config)                    # pre-built
```

### Binding interfaces to implementations

The container's most powerful feature is binding an **interface to an implementation** — depend on the
interface everywhere, swap the concrete in one place (or in a test):

```python
app.bind(Mailer, SmtpMailer)     # anything needing a Mailer gets an SmtpMailer
```

Give a binding a short string alias when convenient:

```python
app.alias("db", Db)
app.make("db")          # same as app.make(Db)
```

### Conditional binding

`bind_if` / `singleton_if` / `scoped_if` register **only when the abstract is not already bound** —
the tool for a package default an application may have overridden first:

```python
app.singleton_if(Clock, SystemClock)   # keeps the app's Clock if one is already bound
```

### Contextual binding

Two consumers can need the *same* interface resolved *differently*. `when…needs…give` expresses that:

```python
(app.when(PhotoController)
    .needs(Filesystem)
    .give(lambda c: c.make(FilesystemManager).disk("s3")))

(app.when(InvoiceController)
    .needs(Filesystem)
    .give(lambda c: c.make(FilesystemManager).disk("local")))
```

Two shorthands cover the common "give me a list of services" and "give me a config value" cases:

```python
app.tag([RateLimit, Csrf], "http.filters")

(app.when(FilterChain).needs("filters").give_tagged("http.filters"))  # the tagged list
(app.when(SearchClient).needs("api_key").give_config("services.search.key", default=None))
```

`give_tagged` injects everything under the tag in registration order; `give_config` reads the bound
config repository at resolve time.

### Binding typed variadics

A constructor's typed `*args` parameter resolves to **every binding of that type**, in registration
order — or to a contextual `give([...])` list when one is set. Nothing bound means an empty tuple:

```python
class Pipeline:
    def __init__(self, *filters: Filter): ...

app.bind(RateLimit)   # each a Filter subclass
app.bind(Csrf)
app.make(Pipeline)    # Pipeline(RateLimit(), Csrf())

(app.when(Pipeline).needs("filters").give([Csrf]))   # explicit set wins
```

### Extending bindings

Wrap or decorate a binding after it's built — useful for adding behavior to a service a package
registered:

```python
app.extend(Mailer, lambda mailer, c: LoggingMailer(mailer))
```

The closure runs on the next resolve. If the service is a **singleton that's already been resolved**,
`extend` applies immediately — so extending late still takes effect everywhere it's already injected.

## Resolving

### The `make` method & autowiring

`make` resolves a type out of the container. If a class's dependencies are themselves resolvable, the
container builds the whole graph — this is **autowiring**:

```python
class Mailer: ...
class WelcomeService:
    def __init__(self, mailer: Mailer):     # the container sees this dependency
        self.mailer = mailer

service = app.make(WelcomeService)          # Mailer is constructed and injected
```

### Automatic injection

You rarely call `make` yourself in app code — controllers, listeners, and jobs are resolved *through*
the container, so their constructor dependencies arrive injected. `make` reads the constructor's type
hints and injects each dependency it can build:

- **Class-typed params** are resolved recursively (`make`-d).
- **Keyword-only params** (`def __init__(self, *, cache): …`) are honored — passed by keyword.
- **Non-injectable annotations** — `typing.Any`, primitives, generics like `list[str]`, an
  unresolvable forward reference — are **not** built. With a default or `Optional`, that default/`None`
  is used; otherwise `make` raises a clear `BindingResolutionError`.

This is why the framework's own middleware (with keyword-only, `Any`-typed ctor params) can be built by
the container per request.

## Method invocation & injection

`call` invokes a function and injects its parameters from the container — how jobs, listeners, and
controller methods get their dependencies:

```python
async def handle(self, transcoder: Transcoder):    # resolved + injected by the worker
    await transcoder.process(self.podcast)
```

To override how a specific method is resolved, register it with `bind_method`:

```python
app.bind_method([ReportJob, "handle"], lambda job, c: job.handle(c.make(Exporter)))
```

## Container events

Run a callback every time a type is resolved — handy for configuring every instance a package hands
out. `resolving` fires as the object is built; `after_resolving` fires right after:

```python
app.resolving(Logger, lambda logger, c: logger.add_context(app="arvel"))
app.after_resolving(Logger, lambda logger, c: logger.flush_buffer())
```

Both fire for every resolve — transient, shared, and the first build of a `scoped` binding.

## Putting it together

Bind an interface once in a provider, depend on that interface everywhere, and never wire the graph by
hand:

```python
# in a provider's register()
app.singleton(Db, lambda c: Db.connect(env("DB_URL")))     # one shared pool
app.bind(Mailer, SmtpMailer)                                # interface → implementation

class ReportService:
    def __init__(self, db: Db, mailer: Mailer): ...         # declares what it needs

async def send_report(request, reports: ReportService):     # resolved through the container
    await reports.mailer.send(await reports.db.fetch_all(...))
```

You wrote three declarations; the container built the graph. Swap `SmtpMailer` for a fake in a test by
rebinding `Mailer` — nothing else changes.

## Common mistakes & gotchas

- **`singleton` holding request state.** A singleton lives for the whole process — don't store
  per-request data on it (use `scoped`), or requests will see each other's state.
- **Binding a concrete you could autowire.** If a class has no interface and resolvable dependencies,
  don't bind it — `make` autowires it. Bind only to map an interface, supply config, or set a lifetime.
- **Circular dependencies.** A → B → A can't be constructed; the container raises rather than looping.
  Break the cycle (a lazy lookup or an event).

## See also

- [Service Providers](providers.md) — where you register bindings at boot.
- [Contracts](contracts.md) — the interfaces you bind implementations to.
- [Queues](queues.md) · [Events](events.md) — both inject via `call`.
