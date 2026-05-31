<p align="center">
  <a href="https://arvel.dev"><img src="https://raw.githubusercontent.com/mohamed-rekiba/arvel/main/docs/site/docs/assets/brand/arvel-logo-dark.svg" alt="Arvel" width="180"></a>
</p>
<p align="center">
    <em>The Laravel of Python — expressive routing, a typed ORM, and first-class async.</em>
</p>
<p align="center">
<a href="https://github.com/mohamed-rekiba/arvel/actions/workflows/ci.yml" target="_blank">
    <img src="https://github.com/mohamed-rekiba/arvel/actions/workflows/ci.yml/badge.svg" alt="CI">
</a>
<a href="https://github.com/mohamed-rekiba/arvel/actions/workflows/security.yml" target="_blank">
    <img src="https://github.com/mohamed-rekiba/arvel/actions/workflows/security.yml/badge.svg" alt="Security">
</a>
<a href="https://pypi.org/project/arvel/" target="_blank">
    <img src="https://img.shields.io/pypi/v/arvel?color=%2334D058&label=pypi%20package" alt="Package version">
</a>
<a href="https://pypi.org/project/arvel/" target="_blank">
    <img src="https://img.shields.io/pypi/pyversions/arvel.svg?color=%2334D058" alt="Supported Python versions">
</a>
<a href="LICENSE" target="_blank">
    <img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="MIT License">
</a>
<img src="https://img.shields.io/badge/mypy%20%26%20pyright-strict-success.svg" alt="Strict types">
</p>

---

**Documentation**: <a href="https://arvel.dev" target="_blank">https://arvel.dev</a>

**Source Code**: <a href="https://github.com/mohamed-rekiba/arvel" target="_blank">https://github.com/mohamed-rekiba/arvel</a>

---

> **Status**: Pre-alpha — `v0.3.0`. Core subsystems are shipped and working; public API may change before `1.0`.

Arvel brings Laravel's developer experience to async Python. Service container, typed config,
Eloquent-style ORM, form requests, queues, events, broadcasting, mail, notifications, cache,
storage, and scheduling — all wired together on top of **FastAPI**, **Pydantic**, and **SQLAlchemy**.
No new router. No new ORM. No bespoke DI framework. Just a coherent layer over the standard stack.

**The key features are:**

- **Artisan-style CLI** — `arvel new`, `arvel make:model`, `arvel migrate`, `arvel queue:work`,
  and 30+ generators. One binary, zero PATH gymnastics.
- **Typed configuration** — every config object is a `pydantic-settings` `BaseSettings`.
  `Config.of(DbConfig)` returns a fully-typed instance; no `os.getenv` scattered everywhere.
- **Arvent ORM** — `Model` on SQLAlchemy with Eloquent-style relations, soft deletes, scopes,
  a schema DSL that compiles to Alembic migrations, and a fluent `QueryBuilder`.
- **Auth** — JWT + session + token guards, `Gate` and `Policy`, bcrypt/argon2 hashing,
  email verification, and password-reset flows.
- **Queues** — `Job`, `Bus`, `Batch`, `Chain`. Four drivers (sync, database, Redis, AMQP),
  retry with exponential backoff, dead-letter queue, and graceful worker shutdown.
- **Events & Broadcasting** — typed `Event` classes, sync and queued listeners, and a
  Reverb-compatible WebSocket server over the Pusher protocol.
- **Mail & Notifications** — `Mailable` ABC, SMTP/log/array drivers, multi-channel
  notifications (mail + database + broadcast).
- **FastAPI-native** — `dep()` resolves any container binding as a `Depends`. Every route
  is a plain `async def`. OpenAPI docs work out of the box.
- **Strict types** — every public symbol passes `mypy --strict` and `pyright --strict` with
  zero errors and zero warnings.

## Requirements

Python 3.14+

## Installation

```bash
# Recommended — bootstraps uv if needed, installs the arvel binary globally
curl -fsSL https://arvel.dev/install.sh | bash
```

Or install from PyPI:

```bash
uv tool install arvel
# or: pipx install arvel
```

## Quick start

### Create a project

```bash
arvel new my-app
cd my-app
```

This generates a Laravel-shaped project layout:

```
my-app/
├── app/
│   ├── http/
│   │   ├── controllers/
│   │   ├── requests/
│   │   └── resources/
│   └── models/
├── bootstrap/
│   ├── app.py
│   └── providers.py
├── config/
├── database/
│   ├── migrations/
│   └── seeders/
├── routes/
│   ├── api.py
│   └── web.py
└── public/
    └── asgi.py          # ASGI entrypoint
```

### Run it

```bash
uv run arvel serve --reload
```

Open `http://127.0.0.1:8000/api/healthz` — you'll see:

```json
{"status": "ok"}
```

### Define a route

Edit `routes/api.py`:

```python
from arvel import Route


@Route.get("/api/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@Route.get("/api/items/{item_id}")
async def show_item(item_id: int) -> dict[str, int]:
    return {"item_id": item_id}
```

### Add a model

```bash
arvel make:model Item --migration
```

Edit `app/models/item.py`:

```python
from decimal import Decimal

from arvel.database import Model, Timestamps, boolean, decimal, id_, string


class Item(Model, Timestamps):
    __tablename__ = "items"

    id: int = id_()
    name: str = string(255)
    price: Decimal = decimal(10, 2)
    is_active: bool = boolean(default=True)
```

Run the migration:

```bash
arvel migrate
```

### Use the ORM in a route

```python
from arvel import Route
from app.models.item import Item


@Route.get("/api/items")
async def index() -> list[dict[str, object]]:
    items = await Item.where(is_active=True).order_by("-created_at").get()
    return [{"id": i.id, "name": i.name, "price": i.price} for i in items]


@Route.get("/api/items/{item_id}")
async def show(item_id: int) -> dict[str, object]:
    item = await Item.find_or_fail(item_id)
    return {"id": item.id, "name": item.name, "price": item.price}
```

Open `http://127.0.0.1:8000/docs` for the auto-generated interactive API docs.

---

## Feature guide

### Typed configuration

```python
from pydantic import SecretStr
from arvel.config import ArvelSettings, register
from arvel.facades import Config


@register
class DbConfig(ArvelSettings):
    url: str = "postgresql+asyncpg://localhost/app"
    password: SecretStr = SecretStr("")
    # env prefix auto-derived: reads DB_URL, DB_PASSWORD


db = Config.of(DbConfig)  # fully typed, no string dict
print(db.url)
```

### Form requests and resources

```python
from arvel import Route
from arvel.http import FormRequest, Resource
from app.models.item import Item


class CreateItemRequest(FormRequest):
    name: str
    price: float

    def rules(self) -> dict[str, object]:
        return {"name": "required|string|max:255", "price": "required|numeric|min:0"}


class ItemResource(Resource):
    def transform(self, item: Item) -> dict[str, object]:
        return {"id": item.id, "name": item.name, "price": item.price}


@Route.post("/api/items")
async def store(request: CreateItemRequest) -> ItemResource:
    item = await Item.create(**request.validated())
    return ItemResource(item)
```

### Auth

```bash
arvel auth:install   # generates guards, migrations, password-reset routes
```

```python
from arvel import Route
from arvel.facades import Auth


@Route.get("/api/me", middleware=["auth"])
async def me() -> dict[str, object]:
    user = Auth.user()
    return {"id": user.id, "email": user.email}


@Route.post("/api/login")
async def login(email: str, password: str) -> dict[str, str]:
    token = await Auth.guard("api").attempt(email, password)
    return {"token": token}
```

### Queues

```python
from arvel.queue import Job
from arvel.facades import Bus, Mail
from app.mail.welcome_mail import WelcomeMail


class SendWelcomeEmail(Job):
    user_id: int

    async def handle(self) -> None:
        from app.models.user import User
        user = await User.find(self.user_id)
        await Mail.to(user.email).send(WelcomeMail(user))


# Dispatch
await Bus.dispatch(SendWelcomeEmail(user_id=42))

# Dispatch with delay
await Bus.dispatch(SendWelcomeEmail(user_id=42).delay(seconds=30))
```

Start the worker:

```bash
arvel queue:work
```

### Events

```python
from arvel.events import Event, listen


class UserRegistered(Event):
    user_id: int
    email: str


@listen(UserRegistered)
async def send_welcome(event: UserRegistered) -> None:
    await Bus.dispatch(SendWelcomeEmail(user_id=event.user_id))


# Fire the event
from arvel.facades import EventBus
await EventBus.dispatch(UserRegistered(user_id=42, email="alice@example.com"))
```

### Mail

```python
from arvel.mail import Mailable
from arvel.facades import Mail


class WelcomeMail(Mailable):
    def __init__(self, name: str) -> None:
        self.name = name

    def build(self) -> "WelcomeMail":
        return self.subject(f"Welcome, {self.name}!").view("emails.welcome")


await Mail.to("alice@example.com").send(WelcomeMail("Alice"))
```

### Scheduling

```python
# routes/console.py
from arvel.scheduling import Schedule


def schedule(s: Schedule) -> None:
    s.command("reports:generate").daily()
    s.call(refresh_cache).every_minute()
    s.job(CleanupExpiredTokens).weekly()
```

Start the scheduler:

```bash
arvel schedule:work
```

### FastAPI interop

Arvel is a FastAPI application under the hood. You can mix plain FastAPI routes with Arvel
routes and use the DI container as a `Depends`:

```python
from fastapi import Depends
from arvel import dep
from app.services.item_service import ItemService

# dep() resolves any container binding as a FastAPI Depends
@Route.get("/api/items/{id}/details")
async def details(id: int, svc: ItemService = Depends(dep(ItemService))) -> dict[str, object]:
    return await svc.get_details(id)
```

---

## Optional extras

Arvel ships with a slim core. Add only what you use:

```bash
uv add "arvel[all]"        # everything at once
uv add "arvel[redis]"      # Redis cache, sessions, queue
uv add "arvel[postgres]"   # asyncpg + psycopg drivers
uv add "arvel[sqlite]"     # aiosqlite driver
uv add "arvel[jwt]"        # JWT guard (pyjwt + authlib)
uv add "arvel[mail]"       # SMTP mail driver (aiosmtplib)
uv add "arvel[queue]"      # Taskiq async broker
uv add "arvel[azure]"      # Azure Blob Storage driver
```

## Companion packages

| Package | Description |
|---|---|
| [`arvel-permission`](https://arvel.dev/permission) | Roles and permissions — Spatie Permission parity for Python |
| [`arvel-image`](https://arvel.dev/image) | Polymorphic media library with automatic image conversions (Pillow) |

```bash
uv add arvel-permission
uv add arvel-image
```

## Stack

Python 3.14+ · FastAPI · Pydantic · pydantic-settings · SQLAlchemy · Alembic · Typer · Taskiq · structlog · argon2-cffi · aiosmtplib

## Type safety

Every public symbol passes both `mypy --strict` and `pyright --strict` — **zero errors, zero warnings**.

- `Any` is not an escape hatch. Introducing one requires an explicit `cast()` with justification.
- `# type: ignore`, `# noqa`, and `# pyright: ignore` are not used to silence findings.
- Pyright runs with `reportUnknownVariableType`, `reportPrivateUsage`, `reportUnusedImport`,
  `reportArgumentType`, and `reportAttributeAccessIssue` all promoted to **error**.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Changes need `mypy --strict` and `pyright --strict` clean,
≥ 90% coverage on `arvel/`, and a Conventional Commit message.

```bash
make sync && make ci
```

## Security

See [SECURITY.md](SECURITY.md) for reporting vulnerabilities. The CI pipeline runs bandit,
semgrep, pip-audit, gitleaks, CycloneDX SBOM generation, and Sigstore signing on every PR.

## License

MIT — see [LICENSE](LICENSE).
