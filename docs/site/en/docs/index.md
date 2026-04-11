# Arvel

**Async-first, type-safe Python web framework inspired by Laravel** — Python 3.14+.

If you have ever wished Laravel’s batteries-included ergonomics could meet modern async Python, you are in the right place. Arvel sits on top of FastAPI and Starlette, brings SQLAlchemy 2.0 for the data layer, and wraps everyday concerns — routing, validation, dependency injection, middleware, and a Typer-powered CLI — in APIs that feel familiar yet stay honest to Python’s type system. Structured logging via structlog and settings through Pydantic round out the story so production apps stay observable and configurable without ceremony.

## What you get

- **HTTP routing** — Laravel-style `Router` with named routes, groups, and FastAPI/OpenAPI underneath.
- **ORM & data layer** — SQLAlchemy 2.0 with typed models, repositories, collections, and migrations-minded workflows.
- **Dependency injection** — A real container with scopes, not a bag of globals.
- **Middleware** — Compose the stack you need; same request lifecycle ideas you know from Laravel, expressed as ASGI.
- **Validation** — Pydantic models at the boundary; keep payloads explicit and friendly to `ty` and your IDE.
- **CLI** — `arvel` commands for serve, database work, caches, and more (Typer).
- **Observability** — structlog-first logging; plug in OpenTelemetry or Sentry when you are ready.

## Quick start

An Arvel app is a directory: configuration and providers under `bootstrap/`, route modules under `routes/`, and an ASGI entry that hands Uvicorn an `Application` from `Application.configure`. Here is a tiny project you can drop into a folder and run.

**1. Layout**

```text
my-app/
  .env
  bootstrap/
    providers.py
  routes/
    web.py
```

**2. Environment** (`.env`)

```bash
APP_NAME=MyApp
APP_ENV=local
APP_DEBUG=true
```

**3. Providers** (`bootstrap/providers.py`)

```python
from arvel.foundation.provider import ServiceProvider


class AppProvider(ServiceProvider):
    async def register(self, container) -> None:
        pass

    async def boot(self, app) -> None:
        pass


providers = [AppProvider]
```

**4. Routes** (`routes/web.py`)

```python
from arvel.http.router import Router

router = Router()

router.get("/", lambda: {"message": "Welcome to Arvel"}, name="home")
```

**5. Run**

From the project root, serve with the bundled CLI (Uvicorn under the hood):

```bash
arvel serve
```

Under the hood, `Application.configure(".")` returns an ASGI app that boots on the first request — no heavy import-time side effects — so tools like Uvicorn and production process managers stay predictable.

## Where to go next

- **[Installation](getting-started/installation.md)** — Get Arvel running on your machine in under five minutes.
- **[Directory Structure](getting-started/directory-structure.md)** — Understand the project layout and conventions.
- **[Routing](basics/routing.md)** — Define endpoints, groups, and named routes.
- **[ORM](orm/getting-started.md)** — Work with typed models, relationships, and the query builder.
- **[Testing](testing/getting-started.md)** — Write your first test with the built-in test client and fakes.
