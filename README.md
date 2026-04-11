<p align="center">
  <strong>Arvel</strong>
</p>

<p align="center">
  <em>Async-first, type-safe Python web framework inspired by Laravel.</em>
</p>

<p align="center">
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.14%2B-blue" alt="Python 3.14+"></a>
  <a href="https://github.com/Mohamed-Rekiba/arvel/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT License"></a>
  <a href="https://pypi.org/project/arvel/"><img src="https://img.shields.io/badge/pypi-v0.1.4-orange" alt="PyPI"></a> <!-- x-release-please-version -->
</p>

> **Alpha Software** — Arvel is under active development. APIs may change between releases. Use it for experimentation and early projects, and expect breaking changes until a stable 1.0 release. The PyPI package is not published yet — install directly from GitHub (see below).

---

If you've ever wished Laravel's batteries-included ergonomics could meet modern async Python, you're in the right place. Arvel sits on top of **FastAPI** and **Starlette**, brings **SQLAlchemy 2.0** for the data layer, and uses **Pydantic** everywhere — request validation, application settings, serialization, and response schemas — so your entire stack speaks the same type language. Structured logging via **structlog** and a **Typer**-powered CLI round out the story so production apps stay observable and configurable without ceremony.

## Features

- **HTTP routing** — Laravel-style `Router` with named routes, groups, middleware, and full FastAPI/OpenAPI underneath
- **ORM & data layer** — SQLAlchemy 2.0 async with typed models (`Mapped[T]`), repositories, query builder, relationships, scopes, soft deletes, observers, and migrations
- **Dependency injection** — A real container with scopes, providers, and auto-wiring
- **Authentication** — JWT guards, OAuth2/OIDC, bcrypt/argon2 hashing, and audit logging
- **Pydantic everywhere** — Request validation, response schemas, application settings (`pydantic-settings`), and serialization all flow through Pydantic, giving you end-to-end type safety that `ty` and your IDE can verify
- **CLI** — `arvel` commands for scaffolding, serving, database work, queues, scheduling, routes, and more (Typer)
- **Mail & notifications** — SMTP driver, notification channels, broadcasting
- **Queue & scheduler** — Background jobs with batching, chaining, and cron-based scheduling
- **Cache, sessions & locks** — Pluggable drivers for caching, session management, and distributed locks
- **File storage** — Abstraction over local and S3-compatible storage
- **Search** — Meilisearch and Elasticsearch integration
- **Observability** — structlog-first logging, OpenTelemetry instrumentation, Sentry integration, health checks
- **Testing** — Built-in `TestClient`, `ModelFactory`, and fakes for cache, mail, queue, storage, and more
- **Security** — Encryption helpers, rate limiting, CORS, and security headers

## Quick start

### Prerequisites

- **Python 3.14+**
- **[uv](https://docs.astral.sh/uv/)** — fast Python package manager (recommended)

  ```bash
  # macOS / Linux
  curl -LsSf https://astral.sh/uv/install.sh | sh

  # Windows
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```

  You can also use `pip` directly, but the examples below assume `uv`.

### Install

> The PyPI package is not published yet. Install from GitHub for now.

**Add to your project:**

```bash
# From GitHub (available now)
uv add git+https://github.com/mohamed-rekiba/arvel@main

# From PyPI (once published)
pip install arvel
# or
uv add arvel
```

**Install the CLI as a standalone tool:**

```bash
# From GitHub (available now)
uv tool install --upgrade --force "git+https://github.com/mohamed-rekiba/arvel.git"

# From PyPI (once published)
uv tool install arvel
# or
pipx install arvel
```

### Scaffold a project

```bash
arvel new my-app
```

Without flags, the CLI walks you through an interactive stack selector — pick a preset or customize each service:

```
? Choose your stack:
❯ Minimal    — sqlite, memory, sync, log, local, collection, memory
  Standard   — postgres, redis, redis, smtp, local, collection, memory
  Full       — postgres, redis, taskiq, smtp, s3, meilisearch, redis
  Custom     — choose each service individually
```

Or skip prompts entirely with `--preset` or individual flags:

```bash
arvel new my-app --preset standard
arvel new my-app --database postgres --cache redis --queue taskiq
arvel new my-app --no-input              # defaults (minimal)
```

### Run the dev server

```bash
cd my-app
arvel serve
```

The app binds to `127.0.0.1:8000` with hot reload enabled. Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.

### Minimal example

Don't want the scaffold? Drop these files into a folder:

```text
my-app/
  .env
  bootstrap/
    providers.py
  routes/
    web.py
```

**`.env`**

```bash
APP_NAME=MyApp
APP_ENV=local
APP_DEBUG=true
```

**`bootstrap/providers.py`**

```python
from arvel.foundation.provider import ServiceProvider


class AppProvider(ServiceProvider):
    async def register(self, container) -> None:
        pass

    async def boot(self, app) -> None:
        pass


providers = [AppProvider]
```

**`routes/web.py`**

```python
from arvel.http.router import Router

router = Router()

router.get("/", lambda: {"message": "Welcome to Arvel"}, name="home")
```

Then run `arvel serve` from the project root.

## Optional extras

Core Arvel stays lean. Install drivers and integrations as extras:

```bash
uv add "git+https://github.com/mohamed-rekiba/arvel@main[pg,redis,smtp]"
```

| Extra | Purpose |
| --- | --- |
| `sqlite` | Async SQLite via aiosqlite |
| `pg` | PostgreSQL via asyncpg |
| `mysql` | Async MySQL drivers |
| `redis` | Redis client with hiredis |
| `smtp` | Async SMTP mail |
| `s3` | S3-compatible object storage |
| `media` | Image handling via Pillow |
| `argon2` | Argon2 password hashing |
| `meilisearch` | Meilisearch search engine |
| `elasticsearch` | Elasticsearch search engine |
| `taskiq` | Background task processing |
| `otel` | OpenTelemetry instrumentation |
| `sentry` | Sentry error tracking |

## CLI

The `arvel` command covers the full development lifecycle:

```bash
arvel serve              # Start the dev server
arvel new <name>         # Scaffold a new project
arvel make model User    # Generate a model
arvel db migrate         # Run database migrations
arvel db seed            # Seed the database
arvel db fresh           # Drop, recreate, migrate, and seed
arvel queue work         # Start the queue worker
arvel schedule run       # Run scheduled tasks
arvel route list         # List registered routes
arvel tinker             # Interactive REPL (IPython)
arvel health             # Check application health
```

Run `arvel --help` for the full command list.

## Development

### Prerequisites

- **Python 3.14+**
- **[uv](https://github.com/astral-sh/uv)** for dependency management
- **Docker** (optional, for integration tests with Postgres, MariaDB, Valkey, etc.)

### Setup

```bash
git clone https://github.com/Mohamed-Rekiba/arvel.git
cd arvel

# Install all dependencies + extras
uv sync --all-extras

# Install pre-commit hooks
uv run pre-commit install
```

For the full development environment with Docker services:

```bash
make setup  # Install deps + start Docker services
```

### Running tests

```bash
# Unit tests (no Docker required)
make test-unit

# Full test suite
make test

# Tests against Docker services (Postgres, MariaDB, Valkey, Mailpit, etc.)
make test-docker

# With coverage
make coverage
```

### Code quality

```bash
make lint       # Ruff check + format check
make typecheck  # ty type checker
make verify     # lint + typecheck + test (full CI gate)
make format     # Auto-format code
```

### Pre-commit hooks

The project uses pre-commit with:

- **Ruff** — linting and formatting
- **ty** — type checking
- **gitleaks** — secret scanning
- Standard hooks (trailing whitespace, merge conflicts, YAML/TOML/JSON validation)

### Documentation

```bash
make docs-serve  # Live-reload docs at http://127.0.0.1:8001
make docs-build  # Build docs site (strict mode)
```

## Tech stack

| Layer | Technology |
| --- | --- |
| HTTP | FastAPI, Starlette, Uvicorn |
| ORM | SQLAlchemy 2.0 (async) |
| Migrations | Alembic |
| Validation & settings | Pydantic, pydantic-settings |
| CLI | Typer |
| Logging | structlog |
| Serialization | orjson |
| Auth | PyJWT, bcrypt |
| Build | Hatchling |
| Lint | Ruff |
| Types | ty |
| Tests | pytest |

## License

MIT
