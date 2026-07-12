# Getting Started

## Meet arvel

arvel is an async-first, type-safe web framework for Python — with the batteries most apps need
already wired: routing, an ORM, validation, views, queues, cache, mail, storage, and a full test
kit. You opt into capabilities; you don't assemble them.

Three ideas shape everything:

- **A light core, lazy engines.** `import arvel` is fast. Every heavy capability (HTTP, database,
  queue, …) lives behind an extra and imports its engine lazily, so your install and cold start
  carry only what you use.
- **Real engines underneath.** Routes compile onto [Litestar](https://litestar.dev), the ORM speaks
  SQLAlchemy Core, views render through Jinja2. You write the ergonomic API and keep an
  inspectable, standard ASGI app — OpenAPI included.
- **One application object.** A request, a queued job, and a CLI command all run against the same
  booted application, with the same container, config, and providers.

arvel targets **Python 3.14+**. Examples use [uv](https://docs.astral.sh/uv/), but pip works.

## Creating an application

### With the installer

Install the arvel CLI once, globally, then scaffold projects with it:

```bash
uv tool install arvel
arvel new blog
```

`arvel new` generates a complete, runnable app — config, routes, migrations, tests — and finishes
the chores a fresh app forgets: it copies `.env.example` to a live `.env` **and generates your
`APP_KEY`**, so encryption (cookies, encrypted casts) works from the first boot. Then:

```bash
cd blog
uv sync                        # install the app's own dependencies
source .venv/bin/activate
arvel serve --reload           # http://127.0.0.1:8000
```

!!! note "The global CLI is for `new`"
    Inside a project, always use the **project's own** `arvel` (the one `uv sync` put in
    `.venv`). The globally-installed tool doesn't carry your app's dependencies, so project
    commands run from it will fail to import your app.

Pick an app shape with `--profile`, and add a working bearer-token auth flow with `--auth`:

```bash
arvel new blog --profile web          # api (default) | web | inertia-vue | minimal
arvel new api --auth                  # login route + token-protected endpoint + tests
```

### Manually

Prefer to grow a project by hand? Add arvel to any package:

```bash
uv add 'arvel[standard]'       # the usual web stack: http, server, console, sqlite, view
uv add arvel                   # or: just the light core (CLI, container, helpers)
```

Capabilities are extras — add them as you need them; each capability's docs page names its extra:

```bash
uv add 'arvel[postgres]'       # the ORM on Postgres (SQLAlchemy + asyncpg)
uv add 'arvel[queue]'          # background jobs (taskiq)
uv add 'arvel[mail]'           # mail
```

## Initial configuration

All of an app's configuration lives in `config/` — plain Python modules, one per section
(`app.py`, `database.py`, `session.py`, …), each reading the environment with sane defaults:

```python
# config/app.py
from arvel import env

config = {
    "name": env("APP_NAME", "arvel"),
    "key": env("APP_KEY", ""),      # generated for you by `arvel new`
    "env": env("APP_ENV", "local"),
    "debug": env("APP_DEBUG", False),
    "timezone": "UTC",
}
```

Environment-specific values belong in `.env` (never committed — the scaffold's `.gitignore`
already excludes it); `.env.example` documents what your app expects. If you ever need to rotate
the key: `arvel key:generate`.

## Databases & migrations

A fresh app is configured for **SQLite** out of the box — zero setup, a file at
`database/database.sqlite`:

```bash
arvel migrate                  # create the tables (the scaffold ships migrations)
```

Moving to Postgres or MySQL is a `.env` change:

```bash
DB_CONNECTION=pgsql
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/blog
```

…plus the matching extra (`uv add 'arvel[postgres]'`). See
[Database](database/index.md) for connections, and
[Migrations](database/migrations.md) for the schema builder.

## The dev server

```bash
arvel serve --reload
```

Your app is a standard ASGI application (`asgi.py` exposes it), so any ASGI server runs it in
production — e.g. `granian asgi:asgi_app` or `uvicorn asgi:asgi_app`. Interactive API docs are
served at `/docs` from the OpenAPI schema your routes generate.

Two more commands you'll use daily:

```bash
arvel route:list               # every registered route, with names + middleware
arvel shell                    # an IPython REPL with your app booted and models loaded
```

## Next steps

Depends on what you're building:

- **An API** — head to [Routing](routing.md), [Validation](validation.md), and
  [Database & ORM](database/index.md); the `--auth` scaffold shows the bearer-token flow
  end to end.
- **A server-rendered app** — [Views](views.md) and [Sessions & Middleware](middleware.md),
  then the same database pages.
- **How it all fits** — [Architecture Concepts](architecture.md) and
  [The Service Container](container.md) explain the application lifecycle and why the test
  kit's `fake()` works.

Every capability page opens with the problem it solves before the API — read them in any order.
