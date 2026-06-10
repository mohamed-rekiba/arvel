---
hide:
  - navigation
  - toc
title: Arvel — the clean stack for Python developers and agents
description: A typed, async-first Python web framework with Laravel-grade developer experience, built on FastAPI + Pydantic + SQLAlchemy.
---

<div class="arvel-hero" markdown>

<p class="arvel-hero__eyebrow">Built on FastAPI · Pydantic · SQLAlchemy</p>

<h1 class="arvel-hero__title">
The web framework for
<span class="arvel-hero__accent">Python developers and agents</span>.
</h1>

<p class="arvel-hero__lede">
Arvel gives Python the Laravel developer experience &mdash; expressive routing, a typed active-record ORM, queues, a scheduler, and a generator CLI &mdash; while staying async to the core and passing <code>mypy --strict</code> end to end.
</p>

<div class="arvel-hero__actions" markdown>
[Get started](getting-started/installation.md){ .md-button .md-button--primary }
[View on GitHub](https://github.com/mohamed-rekiba/arvel){ .md-button }
</div>

</div>

<div class="arvel-pillars" markdown>

<div class="arvel-pillar" markdown>
:material-rocket-launch-outline:{ .arvel-pillar__icon }

### Easy

Scaffold a project in one command. Wire a feature in one import. `Route`, `DB`, `Cache`, `Mail`, and `Bus` come pre-wired through the container, so you write the feature, not the plumbing.

</div>

<div class="arvel-pillar" markdown>
:material-shield-check-outline:{ .arvel-pillar__icon }

### Typed

The whole framework passes `mypy --strict` and `pyright --strict`. Your editor knows every column, route parameter, and config key — so mistakes show up as red squiggles, not 500s at midnight.

</div>

<div class="arvel-pillar" markdown>
:material-lightning-bolt-outline:{ .arvel-pillar__icon }

### Fast

Async by default. Requests, database queries, cache reads, queue dispatch, and mail all run without blocking the event loop — thousands of concurrent connections, no threads or callbacks.

</div>

</div>

## Getting Started

Install the CLI, scaffold a typed project, and you're serving in under a minute.

```console
$ uv tool install arvel       # the CLI, installed globally
$ arvel new blog && cd blog   # a typed project, ready to run
$ arvel serve                 # → http://127.0.0.1:8000
```

> [!NOTE]
> Arvel needs **Python 3.14+**, and works best with [uv](https://docs.astral.sh/uv/). Adding it to an existing project instead? `uv add arvel`.

New to Arvel? Walk the [Quickstart](getting-started/quickstart.md), or read [Installation](getting-started/installation.md) for Docker, optional extras, and CI setup.

## See it in code

No magic strings, no untyped dicts. A route is an `async def`, a model is a typed class, validation is a class the framework runs for you, and slow work goes on a queue with one call.

=== "Route"

    ```python
    from arvel import Route


    @Route.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}
    ```

    Handlers are real FastAPI routes, so path params, Pydantic bodies, and dependency injection all work as you'd expect.

=== "Model"

    ```python
    from arvel.database import Model, Timestamps, id_, string


    class Flight(Model, Timestamps):
        __tablename__ = "flights"

        id: int = id_()
        name: str = string(255)


    flight = await Flight.find(1)     # every terminal call is async
    flights = await Flight.all()
    ```

    Arvent is Arvel's active-record ORM on top of SQLAlchemy's async engine — relationships, casts, scopes, and a fluent query builder included.

=== "Validate"

    ```python
    from typing import Any

    from pydantic import BaseModel, Field
    from arvel import Route
    from arvel.http.requests import FormRequest


    class StoreUserPayload(BaseModel):
        email: str = Field(min_length=3, max_length=254)
        name: str


    class StoreUserRequest(FormRequest[StoreUserPayload]):
        async def authorize(self, request: Any) -> bool:
            return True                  # deny-by-default; opt in here

        def rules(self) -> dict[str, str | list[str]]:
            return {"email": "required|unique:users,email"}


    @Route.post("/api/users")
    async def store(form: StoreUserRequest) -> dict:
        # runs only after parsing, rules, and authorize all pass
        return form.validated().model_dump()
    ```

    Invalid input becomes a structured `422` before your handler runs. Unauthorized requests get a `403`. Your code only sees data it can trust.

=== "Queue"

    ```python
    from arvel.facades.bus import Bus
    from arvel.queue.job import Job


    class ProcessPodcast(Job):
        podcast_id: int

        async def handle(self) -> None:
            ...                          # the slow work, off the request path


    await Bus.dispatch(ProcessPodcast(podcast_id=1))
    ```

    Jobs are typed Pydantic models. Dispatch returns immediately; a worker picks them up. Batches, chains, delays, retries, and backoff are all one field away.

## The `arvel` CLI

One command line for the work you do every day — scaffold a project, generate typed stubs, run migrations, inspect what's registered, and keep workers moving.

=== "First app"

    ```bash
    uv tool install arvel
    arvel new my-app
    cd my-app

    arvel serve              # run under uvicorn
    arvel route:list         # see what registered
    arvel openapi:export     # dump the OpenAPI spec
    ```

=== "Scaffolding"

    ```bash
    arvel make:model Post
    arvel make:migration CreatePostsTable
    arvel make:controller PostController --resource --model=Post
    arvel make:request StorePostRequest
    arvel make:job PublishPost
    arvel make:policy PostPolicy
    ```

    Generated files pass `ruff` and `mypy --strict` straight away. There are 25+ generators — see the [CLI reference](cli/commands.md).

=== "Database"

    ```bash
    arvel migrate            # run pending migrations
    arvel migrate:status     # what's run, what's pending
    arvel migrate:rollback   # undo the last batch
    arvel migrate:fresh      # drop everything, re-run from scratch
    arvel db:seed            # run your seeders
    ```

=== "Workers"

    ```bash
    # Queue
    arvel queue:work                    # process jobs continuously
    arvel queue:work --stop-when-empty  # drain once and exit (CI/cron)
    arvel queue:failed                  # inspect failures
    arvel queue:retry --all             # requeue them

    # Scheduler
    arvel schedule:work                 # ticks every minute, runs due tasks
    arvel schedule:list                 # show tasks and their next run
    ```

## Batteries included

Arvel ships the parts a real app needs, behind one consistent, typed surface:

- **Persistence** — PostgreSQL, MySQL, and SQLite, with Alembic-backed migrations, seeders, and factories.
- **Background work** — queues (`sync`, database, Redis, TaskIQ), a cron-style scheduler, and a dead-letter queue.
- **Messaging** — typed events and listeners, `Mailable` emails, multi-channel notifications, and Reverb broadcasting over WebSockets.
- **Edges** — Redis cache and sessions, S3/GCS/Azure/local storage with signed URLs, JWT auth with refresh rotation, a `Gate` and policies, and field-level encryption.
- **Developer experience** — a generated OpenAPI contract, structured logging, locale-negotiated i18n, and a test kit with `.fake()` doubles.

And the work that doesn't belong in core lives in companion packages: [OAuth login](packages/oauth.md), [roles & permissions](packages/permission.md), [image processing](packages/image.md), [full-text search](packages/search.md), and [audit trails](packages/audit.md). Want a full reference app? Read the [e-commerce kit](kits/ecommerce-kit.md).

## Documentation map

Pick a track based on what you're building:

| Track | Start here | Then |
|---|---|---|
| **New project** | [Installation](getting-started/installation.md) → [Quickstart](getting-started/quickstart.md) | [Directory structure](getting-started/project-structure.md), [Lifecycle](core-concepts/lifecycle.md) |
| **HTTP API** | [Routing](the-basics/routing.md) → [Validation](the-basics/validation.md) | [Resources](the-basics/resources.md), [Error handling](the-basics/error-handling.md) |
| **Database** | [Models & CRUD](orm/models.md) → [Migrations](orm/migrations.md) | [Relationships](orm/relationships.md), [Query builder](orm/query-builder.md) |
| **Background work** | [Queues](features/queues.md) → [Scheduling](features/scheduling.md) | [Events](features/events.md), [CLI workers](cli/commands.md#queue) |
| **SPA / mobile client** | [Frontend integration](frontend/integration.md) | [Authentication](features/authentication.md), export with `arvel openapi:export` |
| **Full-stack reference** | [E-commerce kit](kits/ecommerce-kit.md) | [Companion packages](packages/README.md) |

Every major section has an overview page — click the section name in the sidebar (Getting Started, Core Concepts, Features, …) for a reading order and page index.

## Ready to build?

Install Arvel, scaffold your first app, and ship a typed route in minutes.

[Install Arvel](getting-started/installation.md){ .md-button .md-button--primary }
[Follow the Quickstart](getting-started/quickstart.md){ .md-button }
