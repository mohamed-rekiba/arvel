# Directory Structure

<a name="introduction"></a>
## Introduction

The default Arvel application structure is intended to provide a great starting point for both large and small applications. `arvel new` generates a Laravel-shaped layout — here's what each directory holds and how the app boots.

<a name="the-generated-layout"></a>
## The Generated Layout

```
my-app/
├── app/
│   ├── console/
│   │   └── commands/         # custom CLI commands
│   ├── http/
│   │   ├── controllers/      # controller classes
│   │   ├── middleware/       # HTTP middleware
│   │   ├── requests/         # form requests (validation)
│   │   └── resources/        # JSON resource transformers
│   ├── models/               # ORM models
│   └── providers/            # your service providers
├── bootstrap/
│   ├── app.py                # builds the Application
│   └── providers.py          # your provider list
├── config/
│   ├── app.py                # app name, env, debug, url, timezone, locale
│   ├── database.py
│   ├── logging.py
│   ├── observability.py      # OpenTelemetry / tracing config
│   └── view.py
├── database/
│   ├── factories/            # model factories
│   ├── migrations/           # schema migrations
│   └── seeders/              # seed data
├── public/
│   └── asgi.py               # ASGI entrypoint (public.asgi:asgi)
├── routes/
│   ├── api.py                # JSON API routes
│   ├── web.py                # web routes
│   └── console.py            # scheduled tasks / console routing
├── storage/                  # cache, sessions, views, logs, uploads
├── tests/
│   ├── feature/
│   └── unit/
└── .env                      # local environment variables
```

<a name="how-the-app-boots"></a>
## How the App Boots

`bootstrap/app.py` assembles the application with a fluent builder:

```python
from arvel import Application

_BASE_PATH = ...  # project root


def create_application() -> Application:
    routes_dir = _BASE_PATH / "routes"
    return (
        Application.configure(_BASE_PATH)
        .with_config_dir(_BASE_PATH / "config")
        .with_providers(_BASE_PATH / "bootstrap" / "providers.py")
        .with_routing(
            web=routes_dir / "web.py",
            api=routes_dir / "api.py",
            console=routes_dir / "console.py",
        )
        .create()
    )
```

`public/asgi.py` turns that into the ASGI app the server runs:

```python
from bootstrap.app import create_application

asgi = create_application().into_asgi()
```

`arvel serve` runs `public.asgi:asgi` under uvicorn. See [Application lifecycle](../core-concepts/lifecycle.md) for the full boot sequence.

<a name="where-things-go"></a>
## Where Things Go

| You want to… | Put it in… | Generate with |
|---|---|---|
| Add a JSON endpoint | `routes/api.py` | — |
| Add a model | `app/models/` | `arvel make:model` |
| Validate a request body | `app/http/requests/` | `arvel make:request` |
| Transform a response | `app/http/resources/` | `arvel make:resource` |
| Add business logic | `app/services/` | `arvel make:service` |
| Register bindings / boot logic | `app/providers/` | `arvel make:provider` |
| Add a background job | `app/jobs/` | `arvel make:job` |
| Add a scheduled task | `routes/console.py` | — |

> [!NOTE]
> The skeleton only scaffolds `app/console/`, `app/http/`, `app/models/`, and `app/providers/`. Directories like `app/services/` and `app/jobs/` don't exist until the matching `make:*` command creates them — it creates the directory for you.

<a name="configuration-files"></a>
## Configuration Files

`config/*.py` modules expose plain module-level attributes, read at runtime via dotted keys:

```python
# config/app.py
name: str = _env("APP_NAME", "MyApp")
env: str = _env("APP_ENV", "production").lower()
debug: bool = _env("APP_DEBUG", default=False)
```

```python
from arvel.config import config

app_name = config("app.name")          # reads config/app.py → name
debug = config("app.debug", False)     # never raises; returns default if missing
```

Config keys are **lowercase** and match the module attribute names. See [Configuration](../core-concepts/configuration.md) for both the dotted-key style above and the typed `ArvelSettings` style.

<a name="environment"></a>
## Environment

Local environment lives in `.env`, loaded automatically on boot — it never overrides values already in the process environment. The generated `.env` starts with SQLite and commented-out Postgres/Redis blocks:

```ini
APP_NAME=MyApp
APP_ENV=production
APP_DEBUG=false
APP_URL=http://localhost:8000
APP_TIMEZONE=UTC

LOG_LEVEL=info

DB_CONNECTION=sqlite
# DB_URL=sqlite+aiosqlite:///database/database.sqlite
```

> [!WARNING]
> Never commit secrets. Keep `.env` out of version control and generate `APP_KEY` per environment with `arvel key:generate`.
