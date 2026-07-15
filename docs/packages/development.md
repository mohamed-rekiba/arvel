# Packaging & Extras

"Batteries-included" usually comes with a bill: a fat install where you pay for the database driver,
the queue backend, and the image library whether or not you touch them, and an `import` that drags all
of it into memory on startup. arvel refuses that trade. The core installs **light** — no web server,
no database driver, no heavy libraries — and you add capabilities as **extras**. `import arvel` stays
fast because every engine is loaded lazily, the first time you actually use it. You get the
batteries-included developer experience without the batteries-included weight.

This page covers the extras model, why imports stay light and how that's *enforced* rather than
hoped-for, and how to build your own package that plugs into arvel through an entry point.

## The extras model

Install the core, then opt into what you need:

```bash
uv add arvel                       # light core — no server, no DB driver
uv add 'arvel[http,postgres]'      # + Litestar + SQLAlchemy/asyncpg
uv add 'arvel[standard]'           # a sensible full-stack bundle
```

Each capability maps to an extra that pulls exactly the packages it requires:

| Module / capability | Extra | Packages it installs |
|---------------------|-------|----------------------|
| HTTP, routing, OpenAPI (`arvel.http`) | `http` | litestar |
| ASGI server | `server` | granian, uvicorn |
| ORM + migrations, Postgres (`arvel.database`) | `postgres` | sqlalchemy[asyncio], alembic, asyncpg |
| ORM, MySQL / SQLite | `mysql` / `sqlite` | sqlalchemy, alembic, asyncmy / aiosqlite |
| Vector columns (`t.vector`) + vector search | `vector` | pgvector **+ the Postgres `vector` server extension** |
| Full-text search | `search` | meilisearch |
| Cache / session / throttle / queue over **Redis** | `redis` | redis |
| Queue worker + broker (`arvel.queue`) | `queue` | taskiq, taskiq-redis |
| Views / templates (`arvel.views`) | `view` | jinja2 |
| Auth — JWT / OAuth / 2FA (`arvel.auth`) | `jwt` / `oauth` / `2fa` | pyjwt / httpx-oauth, authlib / pyotp |
| Storage — S3 / GCS / Azure (`arvel.filesystem`) | `s3` / `gcs` / `azure` | s3fs / gcsfs / adlfs |
| Mail (`arvel.mail`) | `mail` | aiosmtplib, markdown-it-py |
| Notifications (`arvel.notifications`) | `notifications` | apprise |
| Media — images / video (`arvel.media`) | `image` / `video` | pillow / av |
| Localization (`arvel.localization`) | `i18n` | babel |
| Telemetry (`arvel.telemetry`) | `telemetry` | opentelemetry-sdk, opentelemetry OTLP + Prometheus exporters, prometheus-client, sentry-sdk |

**Core** (no extra) covers `kernel`, `support`, `dates`, `events`, **validation** (msgspec), and the
helpers. `arvel[standard]` bundles the common set; `arvel[all]` pulls everything. The `vector` extra
needs one step beyond the package — enabling the server extension `CREATE EXTENSION IF NOT EXISTS
vector;` (run it in a migration). Each feature's own page also names its extra under its gotchas.

Forget an extra and arvel tells you exactly which one, instead of surfacing a cryptic `ImportError`
from three libraries deep:

```
No driver 's3'. Install it with: uv add 'arvel[s3]'
```

That's a `MissingExtraError`, raised at the point you reach for the missing capability — the name of
the fix is in the message.

## Why import stays light

`import arvel` pulls in **zero** heavy third-party libraries. Every capability module imports its
engine *inside* the function that needs it, so SQLAlchemy loads the first time you touch a model,
Litestar the first time you serve, and neither before. The CLI's fast paths (`--version`, the
`make:*` generators) go further and import no framework, database, or HTTP code at all — which is why
they return instantly.

This is not a best-effort convention that erodes over time. An **import-linter** contract enforces it
in CI: the light core (`kernel`, `support`, `dates`, `events`, …) is *forbidden* from importing any
heavy library, even transitively. The moment a change pulls SQLAlchemy into the light path — directly
or through some innocent-looking helper — the build fails. The startup guarantee is a test, not a
promise.

## Building a package

A package extends arvel the same way the framework extends itself: it ships a **service provider** and
declares it as an entry point. Installing the package auto-registers the provider — the host app edits
nothing. Here's a Stripe integration, start to finish.

First, declare the provider under the `arvel.providers` entry-point group so arvel discovers it on
install:

```toml
# arvel_stripe/pyproject.toml
[project.entry-points."arvel.providers"]
stripe = "arvel_stripe.provider:StripeServiceProvider"
```

Then the provider itself binds the gateway, defaults its config, and contributes a command and a
publishable config file (see [Service Providers](../providers.md) for every verb):

```python
from arvel.kernel import ServiceProvider

class StripeServiceProvider(ServiceProvider):
    def register(self):
        self.merge_config_from("config/stripe.py", "stripe")          # defaults the app can override
        self.app.singleton("stripe", lambda c: StripeGateway(c.make("config").get("stripe")))

    def boot(self):
        self.commands(stripe_sync_app)                                 # adds `arvel stripe:sync`
        self.publishes({"config/stripe.py": "config/stripe.py"}, tag="config")  # vendor:publish
```

Now `uv add arvel-stripe` in any arvel app makes `app.make("stripe")` resolve, `arvel stripe:sync`
appear in the CLI, and `vendor:publish --tag=config` copy out a `config/stripe.py` the app can edit —
all with no wiring in the host application.

One discipline keeps a package healthy: **depend on arvel's shape, not its guts**. Import from
`arvel.contracts` and the public API only, never from a framework internal. Then a refactor inside
arvel can't break you, and your package is testable on its own against the contracts.

## Common mistakes & gotchas

- **A top-level heavy import in a capability module.** It breaks the startup guarantee — and the
  import-linter fails the build. Import the engine inside the function that uses it.
- **Forgetting the entry point.** A package's provider is discovered only if it's declared under
  `arvel.providers`. Without it, nothing registers, and there's no error to point at.
- **Depending on arvel internals.** Import from `arvel.contracts` / the public API so a framework
  refactor doesn't break your package out from under you.

## How it works

The public `arvel` package uses lazy attribute access (PEP 562): the names you import resolve to their
modules on first access, not at import time. Capability modules then lazy-import their engines inside
functions, so the cost of each engine is paid on first use and never at `import arvel`. Provider
discovery reads the `arvel.providers` entry-point group at boot and merges framework, package, and app
providers into one ordered list. Three import-linter contracts — kernel isolation, the layered module
DAG, and the no-heavy-import startup rule — hold the whole arrangement honest in CI, so "light by
default" stays true as the framework grows.

## See also

- [Service Providers](../providers.md) — the provider a package ships, and every integration verb.
- [Architecture Concepts](../architecture.md) — how "light by default" fits the framework's design.
- [About arvel](../about.md) — the engine behind each extra.
