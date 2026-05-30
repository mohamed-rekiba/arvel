# arvel

The Laravel of Python — built natively on FastAPI + Pydantic + SQLAlchemy, end-to-end type-safe.

> **Status.** Ships: Container, Application, ServiceProvider, Config, support primitives, HTTP, ORM, Cache, Session, Storage, Queue, and Auth (WI-arvel-007). Console, Events, Mail, Notifications, Broadcasting, and Scheduler land in subsequent work items.

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
