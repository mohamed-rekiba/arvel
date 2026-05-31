# arvel

The Laravel of Python — built natively on FastAPI + Pydantic + SQLAlchemy, end-to-end type-safe.

> **Status:** Pre-alpha — `v0.3.0`. Public API may change before `1.0`.

Shipped subsystems: service container, typed config, HTTP (routing, form requests,
resources, middleware), the Arvent ORM (Eloquent-style relations, soft deletes, scopes,
the schema DSL, and a fluent `QueryBuilder`), cache, session, storage, queues, events,
broadcasting, mail, notifications, scheduling, and auth (JWT + session + token guards,
`Gate`/`Policy`, password resets, email verification). See the full docs at
[arvel.dev](https://arvel.dev).

## Install

```bash
pip install arvel
# with extras:
pip install 'arvel[postgres,redis,queue]'
```

## Hello, Arvel

```python
from pathlib import Path
from arvel import Application, ServiceProvider
from arvel.facades import Config
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

## License

MIT
