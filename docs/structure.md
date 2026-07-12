# Directory Structure

The default `arvel new` application ships with a directory layout that scales from a one-file
prototype to a large app without rearranging anything. Nothing here is mandatory — arvel discovers
your code through the bootstrap file, not by convention over the filesystem — but the defaults are a
good place to start.

```
myapp/
├── app/                # your application code
│   ├── controllers/    # route controllers
│   ├── models/         # ORM models
│   ├── providers/      # your service providers
│   └── __init__.py
├── bootstrap/          # how the app is assembled
│   ├── app.py          # create_app() — the one place that configures + builds the app
│   ├── providers.py    # your registered providers
│   └── middlewares.py  # the global/group middleware stack
├── config/             # configuration, one module per section
│   ├── app.py
│   ├── database.py
│   ├── session.py
│   └── …
├── database/
│   ├── migrations/     # schema migrations
│   ├── seeders/        # database seeders
│   └── factories/      # model factories
├── resources/
│   └── views/          # Jinja2 templates
├── routes/
│   ├── web.py          # stateful, browser-facing routes (the "web" group)
│   ├── api.py          # stateless JSON routes (the "api" group, /api prefix)
│   └── console.py      # CLI command definitions
├── tests/
├── asgi.py             # the ASGI entrypoint (asgi_app)
├── pyproject.toml
└── .env                # environment values (never committed)
```

## The bootstrap directory

`bootstrap/app.py` is the heart of the app — the single place that configures and builds it. Both
the CLI (`arvel <command>`) and the ASGI entrypoint load the app from here via `create_app()`:

```python
# bootstrap/app.py
from pathlib import Path
from arvel.kernel import Application

BASE_PATH = Path(__file__).resolve().parent.parent

def create_app() -> Application:
    return (
        Application.configure(str(BASE_PATH))
        .with_config_dir(BASE_PATH / "config")
        .with_providers(BASE_PATH / "bootstrap" / "providers.py")
        .with_middlewares(BASE_PATH / "bootstrap" / "middlewares.py")
        .with_routing(
            web=BASE_PATH / "routes" / "web.py",
            api=BASE_PATH / "routes" / "api.py",
            console=BASE_PATH / "routes" / "console.py",
        )
        .create()
    )
```

`bootstrap/providers.py` lists **your** service providers (framework and installed-package
providers are auto-discovered via entry points — you only register your own), and
`bootstrap/middlewares.py` defines the middleware stack. See
[Service Providers](providers.md) and [Middleware](middleware.md).

## The app directory

`app/` holds the code you write — controllers, models, providers, and anything else your
application needs (jobs, events, policies, services). It starts nearly empty; grow it as you go.
There's no framework rule about sub-package names — `app/services/`, `app/jobs/`, `app/policies/`
are all just packages you import.

## The config directory

Every configuration section is a plain Python module under `config/`, auto-loaded into the
`config("section.*")` store at boot. Each reads the environment with sensible defaults — see
[Configuration](configuration.md).

## The routes directory

Routes are split by group. `web.py` carries stateful, browser-facing routes (cookies, sessions,
CSRF); `api.py` carries stateless JSON routes under an `/api` prefix; `console.py` defines custom
CLI commands. See [Routing](routing.md) and [Console](console.md).

## The database directory

`database/migrations/` holds your schema migrations, `database/seeders/` your seeders, and
`database/factories/` your model factories — the three covered in
[Migrations](database/migrations.md), [Seeding](database/seeding.md), and
[Factories](database/factories.md).

## The resources directory

`resources/views/` holds Jinja2 templates rendered by the [view](views.md) system. Frontend assets
(if you use the Vite integration) live alongside your JS/CSS toolchain — see
[Frontend](frontend.md).
