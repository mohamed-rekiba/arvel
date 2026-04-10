# Installation

Welcome. If you have ever watched Laravel turn a blank folder into something you can actually ship, you already know the feeling Arvel is going for—only here, the runtime is async Python, the router sits on FastAPI and Starlette, and your settings layer is Pydantic all the way down. This page gets you from zero to a running app: requirements, installing the framework, scaffolding a project, optional drivers, and firing up the dev server.

## Requirements

Arvel **0.1.0** targets **Python 3.14 or newer**. The framework ships with async SQLAlchemy 2.x, structlog, Typer for the CLI, and uvicorn for local serving—so you get a modern stack without assembling it by hand.

You can use **pip** or any PEP 621–compatible installer. The team **recommends [uv](https://github.com/astral-sh/uv)** for fast installs, lockfiles, and the same workflow the `arvel new` command expects when it runs `uv sync` for you.

## Install Arvel

Install the framework into your environment (or add it to an existing project):

```bash
pip install arvel
```

With uv:

```bash
uv add arvel
```

That gives you the `arvel` CLI entry point. You can confirm everything wired up correctly:

```bash
arvel --help
```

## Create a new project

The fastest path is the built-in scaffold. It pulls the starter template, renders it with your app name, writes a sensible `.env`, and (unless you opt out) runs `uv sync` and `git init`.

```bash
arvel new project my-app
```

That creates a directory named `my-app` in the current working directory. Prefer a different database up front? Pass `--database` (short: `-d`):

```bash
arvel new project my-app --database postgres
```

Valid values are `sqlite`, `postgres`, and `mysql`. For a custom template registry entry or fork, see `arvel new project --help` for `--template`, `--using`, and `--branch`.

Once the command finishes, step into the project and start the server (next section).

## Optional dependencies

Core Arvel stays lean; drivers and integrations are **extras** you opt into. Install them alongside the base package when you need that capability:

```bash
pip install "arvel[sqlite]"
pip install "arvel[pg]"
pip install "arvel[redis]"
```

Common extras include:

| Extra | Purpose |
| --- | --- |
| `sqlite` | `aiosqlite` for async SQLite |
| `pg` | `asyncpg` for PostgreSQL |
| `mysql` | Async MySQL drivers |
| `redis` | Redis client (with hiredis) |
| `smtp` | Async SMTP mail |
| `s3` | S3-compatible object storage |
| `media` | Image handling (Pillow) |
| `taskiq` | Background tasks |
| `otel` | OpenTelemetry instrumentation |
| `sentry` | Sentry SDK for FastAPI |

Combine extras with commas inside the quotes, for example:

```bash
uv add "arvel[pg,redis,smtp]"
```

## Run the development server

From your project root (where `bootstrap/app.py` lives), start the app:

```bash
arvel serve
```

By default this binds to `127.0.0.1:8000`, enables **reload** on file changes, and discovers your ASGI factory at `bootstrap.app:create_app`. Useful flags:

```bash
arvel serve --host 0.0.0.0 --port 8000
arvel serve --no-reload
arvel serve --workers 4
```

Behind a reverse proxy, you will often set `--root-path` and keep `--proxy-headers` (on by default) so `X-Forwarded-*` headers resolve correctly.

You are installed, scaffolded, and serving. Next, dig into [Configuration](configuration.md) so your `.env` and module settings match how you deploy.
