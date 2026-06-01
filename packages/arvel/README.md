# arvel

The Laravel of Python — built natively on FastAPI + Pydantic + SQLAlchemy, end-to-end type-safe.

> **Status:** Pre-alpha. The public API can still change before `1.0`.

Arvel is a batteries-included application framework for async Python. It layers a service container,
typed configuration, an Eloquent-style ORM (Arvent), an HTTP stack (routing, form requests, API
resources, middleware), cache, sessions, storage, queues, events, broadcasting, mail, notifications,
scheduling, and auth on top of the standard async stack — without replacing FastAPI, Pydantic, or
SQLAlchemy.

Full documentation lives at **[arvel.dev](https://arvel.dev)**.

## Install

```bash
pip install arvel
# with extras:
pip install 'arvel[postgres,redis,queue]'
```

Arvel requires **Python 3.14+**.

## Hello, Arvel

The framework boots through an `Application`. You register configuration and service providers, then
resolve services from the container:

```python
from pathlib import Path

from arvel import Application, ServiceProvider
from arvel.config import ArvelSettings


class AppSettings(ArvelSettings):
    name: str = "MyApp"
    debug: bool = False


class Greeter:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def greet(self, who: str) -> str:
        prefix = "DEBUG: " if self.settings.debug else ""
        return f"{prefix}Hello from {self.settings.name}, {who}!"


class GreeterProvider(ServiceProvider):
    def register(self) -> None:
        self.app.container.singleton(Greeter)


async def main() -> None:
    app = (
        Application.configure(Path("."))
        .with_environment("production")
        .with_config_files([AppSettings])
        .with_providers([GreeterProvider])
        .create()
    )
    await app.boot()

    greeter = app.container.make(Greeter)
    print(greeter.greet("Arvel"))

    await app.shutdown()
```

In a generated project you don't write this by hand — `arvel new` scaffolds `bootstrap/app.py` and
`bootstrap/providers.py`, and `arvel serve` runs the ASGI app for you.

## What's inside

| Area | Highlights |
|---|---|
| **Container & providers** | Constructor injection, singletons, contextual bindings, `dep()` for FastAPI `Depends` |
| **Config** | `ArvelSettings` (pydantic-settings), `@register`, `Config.of(...)`, the `config()` helper |
| **HTTP** | `Route` decorators, `FormRequest` validation, `JsonResource`/`ResourceCollection`, middleware |
| **Arvent ORM** | `Model`, typed relations, soft deletes, scopes, attribute casts, a schema DSL → Alembic |
| **Auth** | JWT / session / token guards, `Gate` and policies, password resets, email verification |
| **Queues** | `Job`, the `Bus` facade, retries with backoff, dead-letter queue, graceful workers |
| **Events** | Typed `Event` models, inline and `ShouldQueue` listeners, the `Event` facade |
| **Mail & notifications** | Mailables (envelope/content), SMTP/log/array drivers, multi-channel notifications |
| **Cache / session / storage** | Pluggable drivers behind `Cache`, `Session`, and `Storage` facades |
| **Scheduling & broadcasting** | Cron-style scheduler, Reverb-compatible WebSocket server |

## CLI

Installing the package puts the `arvel` binary on your PATH. A few common commands:

```bash
arvel new my-app           # scaffold a project
arvel serve --reload       # run the ASGI dev server
arvel make:model Post -m   # generate a model + migration
arvel migrate              # run pending migrations
arvel queue:work           # process queued jobs
arvel schedule:work        # run the scheduler
arvel route:list           # inspect registered routes
arvel about                # show framework + environment info
```

Run `arvel --help` for the full list.

## License

MIT — see [LICENSE](../../LICENSE).
