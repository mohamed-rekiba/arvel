# Service Providers

Something has to decide what's *in* your app — which services exist, where routes and migrations
live, what runs at startup. Service providers are that decision point: the **bootstrap units** of
an arvel app. Each one registers things into the [container](container.md) and then boots them, and
the framework, every installed package, and your own code are all just collections of providers.
That uniformity is what makes arvel modular — adding a capability is adding a provider, nothing more.

This page covers a provider's anatomy (`register` vs `boot`), the integration verbs it uses to
contribute routes/migrations/views/commands, how providers are auto-discovered, and boot order.
Providers are part of the **core** — nothing to install.

## Anatomy

A provider has two phases. `register` binds services into the container; `boot` runs after
*every* provider has registered, so it can safely use anything another provider bound:

```python
from arvel.kernel import ServiceProvider

class PaymentsServiceProvider(ServiceProvider):
    def register(self):
        self.app.singleton("payments", lambda c: StripeGateway(env("STRIPE_KEY")))

    def boot(self):
        # all bindings exist now — safe to wire cross-service behavior
        self.app.make("events").listen(OrderPaid, RecordRevenue)
```

The split matters: **never resolve another provider's binding in `register`** — it may not
exist yet. Do that in `boot`.

## What a provider can do

```python
class BlogServiceProvider(ServiceProvider):
    def register(self):
        self.merge_config_from("config/blog.py", "blog")   # defaults the app can override

    def boot(self):
        self.load_routes_from("routes/blog.py")            # register routes
        self.commands(make_post_app)                        # add CLI commands
        self.publishes({"stubs/blog.html": "resources/views/blog.html"}, tag="views")
        self.publishes_migrations({"database/migrations": "..."}, tag="migrations")
```

- `merge_config_from` — provide config defaults the app can override.
- `load_routes_from` — register the provider's routes. The file is **imported during boot** (after
  providers register, before the app is served), so its module-level `Route.*` definitions land in
  the router and are served — no manual import needed.
- `commands` — add console commands to the host app's `arvel` CLI.
- `publishes` / `publishes_migrations` — expose assets the app can copy out with
  `vendor:publish`.

## Auto-discovery

You don't list providers by hand. arvel discovers them through **entry points**: the framework,
each installed package, and the app all declare their providers, and arvel merges them at boot.
Installing a package like `arvel-stripe` registers its provider automatically — **no edits to
your app**. That's the whole ecosystem story: `uv add` a package and its services light up.

## Boot order

Framework providers register first, then packages, then the app — so your app's `boot` can
override anything a package set up. Within a phase, all `register`s run before any `boot`.

## Common mistakes & gotchas

- **Using a binding in `register`.** Another provider may not have registered it yet. Move the
  usage to `boot`.
- **Heavy work at registration.** `register` runs for *every* provider at every boot — keep it
  to cheap bindings (closures), and defer real work (opening pools, reading files) to `boot` or
  lazy resolution, so startup stays fast.
- **Forgetting the entry point.** A package's provider is only discovered if it's declared as an
  entry point — without it, the services never register.

## How it works

At boot the kernel collects provider classes from the entry-point groups (framework + packages
+ app), instantiates each with the application, calls every provider's `register` (populating
the container), then calls every provider's `boot`. Because discovery is entry-point based and
the two-phase split guarantees all bindings exist before any boot runs, packages compose
cleanly without the app wiring them together.

## See also

- [Service Container](container.md) — what providers register into.
- [Console](console.md) — providers contribute commands; [Routing](routing.md) — and routes.
