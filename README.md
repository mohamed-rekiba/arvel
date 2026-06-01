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
    <img src="https://img.shields.io/pypi/v/arvel?color=%2334D058" alt="Package version">
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

> **Status**: Pre-alpha. Core subsystems ship and work today, but the public API can still change before `1.0`.

Arvel brings Laravel's developer experience to async Python. You get a service container, typed
configuration, an Eloquent-style ORM, form requests, API resources, queues, events, broadcasting,
mail, notifications, cache, sessions, storage, and scheduling — all wired together on top of
**FastAPI**, **Pydantic**, and **SQLAlchemy**. No new router. No new ORM. No bespoke DI framework.
Just one coherent layer over the standard async stack.

## Why Arvel

- **Artisan-style CLI** — `arvel new`, `arvel make:model`, `arvel migrate`, `arvel queue:work`, and
  60+ commands. One binary, no PATH gymnastics.
- **Typed configuration** — every config object is a `pydantic-settings` `BaseSettings`.
  `Config.of(DbConfig)` returns a fully-typed instance instead of stringly-typed dict lookups.
- **Arvent ORM** — `Model` on SQLAlchemy with Eloquent-style relations, soft deletes, scopes,
  attribute casting, a schema DSL that compiles to Alembic migrations, and a fluent query builder.
- **Auth** — JWT, session, and token guards, `Gate` and policies, argon2/bcrypt hashing, email
  verification, and password-reset flows.
- **Queues** — Pydantic `Job` classes, the `Bus` facade, retries with backoff, a dead-letter queue,
  and graceful worker shutdown across sync, database, Redis, and TaskIQ backends.
- **Events & broadcasting** — typed `Event` models, inline and queued listeners, and a
  Reverb-compatible WebSocket server over the Pusher protocol.
- **Mail & notifications** — mailables with envelope/content, SMTP/log/array drivers, and
  multi-channel notifications (mail + database + broadcast).
- **FastAPI-native** — `dep()` resolves any container binding as a `Depends`, every route is a plain
  `async def`, and OpenAPI docs work out of the box.
- **Strict types** — every public symbol passes `mypy --strict` and `pyright --strict` with zero
  errors and zero warnings.

## Requirements

Python 3.14+

## Installation

```bash
# Recommended — bootstraps uv if needed, installs the arvel binary globally
curl -fsSL https://arvel.dev/install.sh | bash
```

Or from PyPI:

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

This generates a Laravel-shaped layout:

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

Open `http://127.0.0.1:8000/api/healthz`:

```json
{"status": "ok"}
```

### Define a route

```python
# routes/api.py
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

```python
# app/models/item.py
from decimal import Decimal

from arvel.database import Model, Timestamps, boolean, decimal, id_, string


class Item(Model, Timestamps):
    __tablename__ = "items"

    id: int = id_()
    name: str = string(255)
    price: Decimal = decimal(10, 2)
    is_active: bool = boolean(default=True)
```

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
    return [{"id": i.id, "name": i.name, "price": str(i.price)} for i in items]


@Route.get("/api/items/{item_id}")
async def show(item_id: int) -> dict[str, object]:
    item = await Item.find_or_fail(item_id)
    return {"id": item.id, "name": item.name, "price": str(item.price)}
```

Open `http://127.0.0.1:8000/docs` for the auto-generated interactive API docs.

---

## A quick tour

### Typed configuration

```python
from pydantic import SecretStr

from arvel.config import ArvelSettings, register
from arvel.facades import Config


@register
class DbConfig(ArvelSettings):
    url: str = "postgresql+asyncpg://localhost/app"
    password: SecretStr = SecretStr("")
    # env prefix is auto-derived: reads DB_URL, DB_PASSWORD


db = Config.of(DbConfig)  # fully typed, no string keys
print(db.url)
```

### Form requests and resources

```python
from arvel import Route
from arvel.http import FormRequest, JsonResource
from app.models.item import Item


class CreateItemRequest(FormRequest):
    name: str
    price: float

    def rules(self) -> dict[str, object]:
        return {"name": "required|string|max:255", "price": "required|numeric|min:0"}


class ItemResource(JsonResource[Item]):
    def to_dict(self, request: object) -> dict[str, object]:
        return {"id": self.resource.id, "name": self.resource.name, "price": str(self.resource.price)}


@Route.post("/api/items")
async def store(form: CreateItemRequest, request: object) -> object:
    item = await Item.create(**form.validated().model_dump())
    return ItemResource(item).response(request)
```

### Auth

```bash
arvel auth:install   # generates guards, migrations, and password-reset routes
```

```python
from arvel import Route
from arvel.facades.auth import Auth
from arvel.http.middleware import Authenticate
from starlette.requests import Request


@Route.get("/api/me", middleware=[Authenticate("api")])
async def me(request: Request) -> dict[str, object]:
    user = await Auth.user(request)
    return {"id": user.id, "email": user.email}


@Route.post("/api/login")
async def login(request: Request) -> dict[str, bool]:
    body = await request.json()
    ok = await Auth.attempt({"email": body["email"], "password": body["password"]}, request)
    return {"authenticated": ok}
```

### Queues

```python
from arvel.queue.job import Job
from arvel.facades.bus import Bus
from arvel.facades.mail import Mail
from app.mail.welcome_mail import WelcomeMail


class SendWelcomeEmail(Job):
    user_id: int

    async def handle(self) -> None:
        from app.models.user import User

        user = await User.find_or_fail(self.user_id)
        await Mail.to(user.email).send(WelcomeMail(user.name))


# Dispatch now
await Bus.dispatch(SendWelcomeEmail(user_id=42))

# Dispatch after a delay — `delay` is a job field (seconds or timedelta)
await Bus.dispatch(SendWelcomeEmail(user_id=42, delay=30))
```

```bash
arvel queue:work
```

### Events

```python
from arvel.events.event import Event
from arvel.events.listener import Listener
from arvel.facades.event import Event as EventFacade


class UserRegistered(Event):
    user_id: int
    email: str


class SendWelcome(Listener[UserRegistered]):
    async def handle(self, event: UserRegistered) -> None:
        await Bus.dispatch(SendWelcomeEmail(user_id=event.user_id))


# Register the mapping in a provider's boot phase:
#   dispatcher = self.app.make(EventDispatcher)
#   dispatcher.listen(UserRegistered, SendWelcome)

await EventFacade.dispatch(UserRegistered(user_id=42, email="alice@example.com"))
```

### Mail

```python
from arvel.mail.mailable import Mailable
from arvel.mail.envelope import Envelope
from arvel.mail.content import Content
from arvel.facades.mail import Mail


class WelcomeMail(Mailable):
    def __init__(self, name: str) -> None:
        self.name = name

    def envelope(self) -> Envelope:
        return Envelope(from_address="hello@example.com", to=["placeholder@example.com"], subject=f"Welcome, {self.name}!")

    def content(self) -> Content:
        return Content(html_view="emails/welcome.html", data={"name": self.name})


await Mail.to("alice@example.com").send(WelcomeMail("Alice"))
```

### Scheduling

```python
# app/console/kernel.py
from arvel.scheduling import Schedule


def schedule(s: Schedule) -> None:
    s.command("reports:generate").daily()
    s.call(refresh_cache).everyMinute()
    s.job(CleanupExpiredTokens).daily()
```

```bash
arvel schedule:work
```

### FastAPI interop

Arvel *is* a FastAPI app under the hood. Mix plain FastAPI routes with Arvel routes, and resolve any
container binding as a `Depends`:

```python
from fastapi import Depends

from arvel import Route, dep
from app.services.item_service import ItemService


@Route.get("/api/items/{item_id}/details")
async def details(item_id: int, svc: ItemService = Depends(dep(ItemService))) -> dict[str, object]:
    return await svc.get_details(item_id)
```

---

## Optional extras

Arvel ships a slim core. Add only what you use:

```bash
uv add "arvel[all]"        # everything at once
uv add "arvel[redis]"      # Redis cache, sessions, queue
uv add "arvel[postgres]"   # asyncpg + psycopg drivers
uv add "arvel[sqlite]"     # aiosqlite driver
uv add "arvel[jwt]"        # JWT guard (pyjwt + authlib)
uv add "arvel[mail]"       # SMTP mail driver (aiosmtplib)
uv add "arvel[queue]"      # TaskIQ async broker
uv add "arvel[s3]"         # S3 storage driver (aioboto3)
```

## Companion packages

| Package | What it adds |
|---|---|
| [`arvel-permission`](packages/arvel-permission) | Roles and permissions — Spatie Permission parity |
| [`arvel-image`](packages/arvel-image) | Pillow-backed image transforms + a polymorphic media library |
| [`arvel-oauth`](packages/arvel-oauth) | OAuth2/OIDC login (Google, GitHub, Microsoft, Apple, generic OIDC) |
| [`arvel-search`](packages/arvel-search) | Scout-style full-text search (Meilisearch, Elasticsearch, database) |
| [`arvel-audit`](packages/arvel-audit) | Automatic audit trail and a fluent activity log |
| [`arvel-ecommerce-demo`](packages/arvel-ecommerce-demo) | A full-stack reference app exercising the framework |

```bash
uv add arvel-permission arvel-image
```

## Stack

Python 3.14+ · FastAPI · Starlette · Pydantic · pydantic-settings · SQLAlchemy · Alembic · Typer ·
TaskIQ · structlog · OpenTelemetry · argon2-cffi · aiosmtplib

## Type safety

Every public symbol passes both `mypy --strict` and `pyright --strict` — **zero errors, zero
warnings**.

- `Any` is not an escape hatch. Introducing one needs an explicit `cast()` with a reason.
- `# type: ignore`, `# noqa`, and `# pyright: ignore` aren't used to silence findings.
- Pyright runs with `reportUnknownVariableType`, `reportPrivateUsage`, `reportUnusedImport`,
  `reportArgumentType`, and `reportAttributeAccessIssue` all promoted to **error**.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Changes need `mypy --strict` and `pyright --strict` clean,
≥ 90% coverage on `arvel/`, and a Conventional Commit message.

```bash
make sync && make ci
```

## Security

See [SECURITY.md](SECURITY.md) to report vulnerabilities. CI runs bandit, semgrep, pip-audit,
gitleaks, CycloneDX SBOM generation, and Sigstore signing on every PR.

## License

MIT — see [LICENSE](LICENSE).
