# Packaging & Extras

A batteries-included framework usually means a heavy install — you pay for the database driver,
the queue backend, and the image library whether or not you use them. arvel refuses that trade-off:
the core installs light (no web server, no database driver, no heavy libraries), you add capabilities
as **extras**, and `import arvel` stays fast because every engine is loaded lazily, the first time
you actually use it. Cold-start stays quick and the dependency tree stays honest.

This page covers how extras work, why imports stay light, and how to ship your own package that
plugs into arvel through an entry point.

## The extras model

Install only what you use:

```bash
uv add arvel                       # light core
uv add 'arvel[http,postgres]'      # + Litestar + SQLAlchemy/asyncpg
uv add 'arvel[standard]'           # a sensible full-stack bundle
```

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
| Telemetry | `telemetry` | opentelemetry-sdk, sentry-sdk |

**Core** (no extra) covers `kernel`, `support`, `dates`, `events`, **validation** (msgspec), and
the helpers. `arvel[standard]` bundles the common set; `arvel[all]` pulls everything. The `vector`
extra needs one step beyond the package — enabling the server extension
`CREATE EXTENSION IF NOT EXISTS vector;` (run it in a migration). Each feature's own page also
names its extra under "Common mistakes & gotchas."

If you call a feature whose extra isn't installed, arvel raises a **`MissingExtraError`** telling
you exactly which to add — no cryptic `ImportError`:

```
No driver 's3'. Install it with: uv add 'arvel[s3]'
```

## Why import stays light

`import arvel` pulls in **zero** heavy third-party libraries. Each capability module imports its
engine *inside* the function that needs it, so the cost is paid only when you use that feature —
and the CLI's fast paths (`--version`, `make:*`) import no framework, DB, or HTTP code at all.

This isn't best-effort: an **import-linter** contract enforces it in CI. The light core
(`kernel`, `support`, `dates`, `events`, …) is forbidden from importing any heavy library, even
transitively. A change that pulls SQLAlchemy into the light path fails the build.

## Building a package

A package extends arvel by shipping a **service provider** declared as an entry point. Installing
the package auto-registers the provider — no edits to the host app (see
[Service Providers](providers.md)):

```toml
# your package's pyproject.toml
[project.entry-points."arvel.providers"]
stripe = "arvel_stripe.provider:StripeServiceProvider"
```

```python
class StripeServiceProvider(ServiceProvider):
    def register(self):
        self.app.singleton("stripe", lambda c: StripeGateway(c.make("config")))
    def boot(self):
        self.commands(stripe_sync_app)            # adds `arvel stripe:sync`
        self.publishes({"config/stripe.py": "config/stripe.py"})   # vendor:publish
```

A well-behaved package imports only `arvel.contracts` (plus the public API), so it depends on the
*shape* of arvel, not its internals — which keeps it decoupled and independently testable.

## Common mistakes & gotchas

- **A top-level heavy import in a capability module.** It breaks the startup NFR (and the
  import-linter). Import the engine inside the function that uses it.
- **Forgetting the entry point.** A package's provider is only discovered if it's declared under
  `arvel.providers` — without it, nothing registers.
- **Depending on `arvel` internals from a package.** Import from `arvel.contracts` / the public
  API so a framework refactor doesn't break you.

## How it works

The public `arvel` package uses lazy attribute access (PEP 562): the names you import resolve to
their modules on first access, not at import time. Capability modules then lazy-import their
engines inside functions. Provider discovery reads the `arvel.providers` entry-point group at
boot and merges framework + package + app providers. Three import-linter contracts (kernel
isolation, the layered DAG, and the no-heavy-import startup rule) keep the whole thing honest in
CI.

## See also

- [Service Providers](providers.md) — how a package registers itself.
- [About arvel](about.md) — the engines behind each extra.
