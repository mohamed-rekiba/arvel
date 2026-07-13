<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/arvel-mark-dark.svg">
  <img src="docs/assets/arvel-mark.svg" alt="arvel" width="96" height="96">
</picture>

# arvel

**The batteries-included, async-first web framework for Python** — type-safe and modular.

Expressive facades, an Active-Record ORM, a real queue, auth, mail, caching, views and a
powerful CLI — one coherent, fully-typed, `async`/`await`-native toolkit. You get a productive,
high-level developer experience without giving up Python's type system or performance.

</div>

---

## Install

```bash
uv add arvel                 # light core — no heavy dependencies
uv add 'arvel[standard]'     # the common set: http, db, queue, cache, view, mail, image
uv add 'arvel[all]'          # everything
```

Requires **Python 3.14+**. Capabilities are opt-in [extras](#extras) — you install only what you use,
and `import arvel` stays light because engines are imported lazily.

## Quickstart

```bash
arvel new blog            # scaffold a new app
cd blog && uv sync
source .venv/bin/activate # activate the virtualenv
arvel serve --reload      # http://127.0.0.1:8000
```

`arvel new` gives you a runnable project: an ASGI entrypoint, a `bootstrap/app.py` factory, web/api
route groups, config files, a `User` model with migrations and a factory, and a test suite.

## A taste

**Routing** — define routes with the `Route` facade; web (stateful) and api (JSON) groups:

```python
from arvel import Route, Schema

async def show(request):
    return {"hello": request.path_param("name")}

Route.get("/hello/{name}", show, name="hello")

class CreatePost(Schema):      # typed request/response → automatic OpenAPI at /schema
    title: str

async def store(request, data: CreatePost) -> CreatePost:
    return data

Route.post("/posts", store, name="posts.store")
```

**ORM** — an Active-Record model on SQLAlchemy Core:

```python
from arvel import Model

class Post(Model):
    __fillable__ = ["title", "body"]
    __casts__    = {"published": "bool", "meta": "json"}

post = await Post.create(title="Hello", body="…")
posts = await Post.where("published", True).order_by("created_at", "desc").get()
await Post.with_("author").get()          # eager-load relations — no N+1
```

**Validation** — concise rules, returning only the validated data:

```python
from arvel import Validator

data = Validator(request_body, {
    "email": "required|email",
    "age":   "nullable|integer|min:18",
}).validate()
```

**Queues, authorization, mail, cache** — the facades you'd expect, all `async`:

```python
from arvel import Job, Gate, Mail, Cache

await SendWelcome.dispatch(user_id=42)            # background job
await SendWelcome.dispatch_after(600, user_id=42) # …or run it in 10 minutes
if await Gate.allows("update", post): ...         # authorization
await Mail.to(user).send(WelcomeMail())           # mailables
await Cache.remember("stats", 300, compute_stats) # cache-aside
```

More: notifications, events & listeners, task scheduling, file storage (local/S3/GCS/Azure),
localization, server-rendered views, and a rich `Str`/`Arr`/`Collection` helper set.

## Why arvel

- **Batteries included, async-first.** Routing, ORM, queue, cache, auth, mail, views, CLI — one
  coherent DX, built `async`/`await`-native from the ground up.
- **Type-safe.** Strict typing across the public API, so your editor and CI catch mistakes before
  runtime — no stub-chasing.
- **Lightweight & modular.** One package, opt-in extras, lazy imports. You pay only for what you use,
  and the CLI stays fast.
- **Convention over configuration.** Sensible defaults, expressive facades, and a familiar project
  layout — scaffold and ship without wiring boilerplate.

## The four gates

Engineering guarantees enforced in CI from the first commit:

- **G1 — boundaries.** `import-linter` keeps modules honest: kernel isolation, a layered DAG, and no
  heavy import at module load.
- **G2 — startup.** `import arvel` pulls **zero** heavy libraries; the CLI stays snappy.
- **G3 — types.** Strict `mypy` **and** `pyright` on every public API.
- **G4 — stack fidelity.** Each capability is built on its mandated engine (Litestar, SQLAlchemy
  Core, whenever, Typer, …) — verified by a per-module test.

## Extras

| Extra | Adds |
|-------|------|
| `http`, `server` | Litestar routing · the granian/uvicorn dev server |
| `sqlite`, `postgres`, `mysql` | SQLAlchemy + the matching async driver + Alembic |
| `queue`, `queue-redis`, `queue-amqp` | taskiq jobs · Redis broker · RabbitMQ/AMQP broker |
| `redis` | cashews caching (Redis backend) |
| `jwt`, `oauth`, `2fa` | JWT tokens · OAuth providers · TOTP two-factor (auth is core) |
| `mail`, `notifications` | SMTP mail · multi-channel notifications (Apprise) |
| `view` | Jinja2 templating |
| `s3`, `gcs`, `azure`, `supabase` | filesystem disks |
| `image`, `video`, `media` | media handling (Pillow / PyAV) |
| `search`, `vector` | Meilisearch · pgvector |
| `i18n`, `telemetry` | Babel localization · OpenTelemetry/Sentry |

`arvel[standard]` bundles the everyday set; `arvel[all]` installs everything.

## Development

```bash
uv venv && uv pip install -e '.[dev]'
./tools/validate.sh    # ruff · mypy · pyright · import-linter · bandit · pip-audit · pytest
```

## Inspired by

If you're coming from PHP, arvel will feel familiar: facades, the service container, providers,
migrations, factories, gates & policies, and a project layout are all here.
Arvel is built natively for async Python, embraces the type system end to end, and stands
on best-in-class Python engines (Litestar · SQLAlchemy Core · Alembic · whenever · Typer · taskiq ·
Babel · msgspec · cashews · fsspec · Jinja2).

## License

[MIT](LICENSE).
