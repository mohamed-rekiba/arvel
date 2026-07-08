# Service Providers

Something has to decide what's *in* your application — which services exist, where the routes and
migrations live, what runs at startup. In arvel that decision lives in one place: **service
providers**. A provider is a small class that registers services into the [container](container.md)
and then boots them, and *everything* is a provider — the framework's own features, every package
you install, and your application's code are all just collections of providers the kernel loads in
order. That uniformity is the whole trick: adding a capability to an arvel app is adding a provider,
nothing more.

This page walks through a provider's two phases, builds one end to end, covers every verb a provider
uses to contribute routes/migrations/views/commands/config, and explains auto-discovery, boot order,
and deferring an expensive provider until it's needed. Providers are part of the **core** — nothing
to install.

## The two phases: register and boot

Every provider has two methods, and the difference between them is the single most important thing
to understand about the system:

```python
from arvel.kernel import ServiceProvider

class PaymentsServiceProvider(ServiceProvider):
    def register(self):
        # phase 1 — bind services. Runs for EVERY provider before any boot().
        self.app.singleton("payments", lambda c: StripeGateway(c.make("config").get("services.stripe")))

    def boot(self):
        # phase 2 — wire things together. Every binding in the app exists now.
        self.app.make("events").listen(OrderPaid, RecordRevenue)
```

`register` **only binds**. It runs for every provider first, and while it runs you cannot assume any
*other* provider's services exist yet — so resolving something in `register` is a bug waiting to
happen. Do nothing there but hand the container closures.

`boot` runs **after every provider has registered**, so by the time it executes the whole container
is populated and it's safe to reach across services — listen for another provider's events, read
config another provider merged, register routes that reference bound services. `boot` may be `async`
when it needs to do async setup:

```python
    async def boot(self):
        await self.app.make("payments").warm_up()   # async boot is awaited by the kernel
```

Keep that split and providers compose cleanly no matter what order they load in. Break it — resolve
in `register` — and your app works only by the accident of load order, until it doesn't.

## Building a provider

Here's the whole lifecycle of a feature, wired as one provider. Say you're adding a blog: it has its
own config, routes, migrations, a CLI command, and a view namespace.

```python
from arvel.kernel import ServiceProvider

class BlogServiceProvider(ServiceProvider):
    def register(self):
        # bind the feature's services and default its config
        self.app.singleton("blog.feed", lambda c: FeedBuilder(c.make("db")))
        self.merge_config_from("config/blog.py", "blog")

    def boot(self):
        self.load_routes_from("routes/blog.py")               # URL map
        self.load_migrations_from("database/blog")            # schema
        self.load_views_from("resources/views/blog", "blog")  # templates as blog::post
        self.commands(blog_app)                               # `arvel blog:publish`
```

That's a complete, self-contained feature. Drop this provider into any arvel app — declare it (or
ship it as a package, below) — and the blog's routes serve, its migrations run under `migrate`, its
`blog::post` templates resolve, and `arvel blog:publish` appears in the CLI. The host app wrote zero
glue code.

### The integration verbs

The methods a provider calls in `boot` to contribute to the host application:

| Verb | Contributes |
|------|-------------|
| `merge_config_from(source, key)` | Config defaults under `key`. The app's own values **win** — this only fills gaps, so a package ships sensible defaults the app can override. `source` is a config file path or a mapping. |
| `load_routes_from(path)` | A routes file. It's imported during boot, so its module-level `Route.*` definitions land in the router and serve — no manual import. |
| `load_migrations_from(path)` | A migrations directory, picked up by `migrate` alongside the app's own. |
| `load_views_from(path, namespace)` | A template directory under a namespace, so `namespace::template` resolves to it — how a package ships overridable views. |
| `load_translations_from(path, namespace)` | A translations directory under a namespace for `namespace::key` lookups. |
| `commands(*cmds)` | Console commands, merged into the host app's `arvel` CLI. |
| `publishes(mapping, tag=...)` | Files the app can copy into its own tree with `vendor:publish` — stub views, config, assets. Group them under a `tag`. |
| `publishes_migrations(paths, tag="migrations")` | Migrations the app publishes into its own migrations directory to own and edit. |

The `load_*` verbs *reference* a package's assets in place; `publishes` *copies* them into the app so
the app owns them. A package typically `load_views_from` for the working defaults **and** `publishes`
the same views under a `views` tag, so an app that wants to customize them runs
`vendor:publish --tag=views` and edits its own copy.

## Auto-discovery

You never maintain a list of providers by hand. arvel discovers them through **entry points**: the
framework, every installed package, and your app each declare their providers under the
`arvel.providers` entry-point group, and the kernel merges them at boot.

```toml
# your app's (or package's) pyproject.toml
[project.entry-points."arvel.providers"]
blog = "app.providers.blog:BlogServiceProvider"
```

The payoff is the entire ecosystem story: `uv add arvel-stripe` and its provider registers itself —
its services, routes, and commands light up with **no edits to your app**. Uninstall it and they're
gone. There is no central registry to keep in sync.

## Boot order

Providers load in a deterministic order — **framework first, then packages, then your app** — and
within that, all `register`s run before any `boot`. Two consequences you can rely on:

- Because every `register` precedes every `boot`, any provider's `boot` sees the complete container.
- Because your app loads **last**, its `boot` runs after every package's — so your app gets the final
  word, and can override or reconfigure anything a package set up.

## Deferred providers

A provider whose services are expensive to construct — but rarely used in a given request — can
**defer**: it isn't booted until something actually resolves one of the contracts it supplies.
Declare those contracts in `provides()`:

```python
class ReportingServiceProvider(ServiceProvider):
    def register(self):
        self.app.singleton("reports", lambda c: ReportEngine(c.make("db")))

    def provides(self):
        return ["reports"]        # non-empty → this provider is deferred
```

Now `ReportEngine` is only built the first time someone resolves `"reports"`. A returned empty list
(the default) means the provider is eager — booted at startup like any other. Defer the heavy,
seldom-hit provider; leave the rest eager.

## Common mistakes & gotchas

- **Resolving a binding in `register`.** Another provider may not have registered it yet. Anything
  that *uses* a service — as opposed to binding one — belongs in `boot`.
- **Heavy work at registration.** `register` runs for every provider on every boot; keep it to cheap
  closures. Opening a pool, reading a file, warming a cache — defer to `boot` or lazy resolution, so
  startup stays fast.
- **Forgetting the entry point.** A provider is only discovered if it's declared under
  `arvel.providers`. No entry point, no registration, no error — the services just silently never
  exist.
- **Deferring a provider with side effects at boot.** `provides()` skips `boot` until a contract is
  resolved. If your `boot` also registers routes or a schedule, deferring it means those never wire
  up until something touches the service. Only defer pure service providers.

## How it works

At boot the kernel reads the `arvel.providers` entry-point groups (framework + packages + app),
instantiates each provider class with the application, and runs the two phases in order: every
`register` first — populating the container — then every eager provider's `boot`. A deferred
provider (non-empty `provides()`) is held back; the container records which contracts it supplies and
boots it lazily the first time one of them is resolved. The `load_*` verbs don't act immediately —
they append to the application's route/migration/view/translation registries, which the kernel drains
once when it compiles the app. Because discovery is entry-point based and the register-before-boot
split guarantees a complete container, providers from wholly independent packages compose without any
of them knowing about each other.

## See also

- [Service Container](container.md) — what providers register into, and how bindings resolve.
- [Packaging & Extras](packaging.md) — shipping your provider as an installable package.
- [Configuration](configuration.md) — the config `merge_config_from` defaults into.
- [Console](console.md) — the commands a provider contributes; [Routing](routing.md) — its routes.
