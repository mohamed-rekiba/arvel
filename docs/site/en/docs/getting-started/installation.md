# Installation

Welcome. If you have ever watched Laravel turn a blank folder into something you can actually ship, you already know the feeling Arvel is going for—only here, the runtime is async Python, the router sits on FastAPI and Starlette, and your settings layer is Pydantic all the way down. This page gets you from zero to a running app: requirements, installing the framework, scaffolding a project, optional drivers, and firing up the dev server.

/// admonition | Alpha Software
    type: warning

Arvel is under active development. APIs may change between releases. Use it for experimentation and early projects, and expect breaking changes until a stable 1.0 release.
///

## Requirements

- **Python 3.14+**
- **[uv](https://docs.astral.sh/uv/)** — fast Python package manager (recommended)

Arvel ships with async SQLAlchemy 2.x, structlog, Typer for the CLI, and uvicorn for local serving—so you get a modern stack without assembling it by hand.

You can use **pip** or any PEP 621–compatible installer, but the team **recommends uv** for fast installs, lockfiles, and the same workflow the `arvel new` command expects when it runs `uv sync` for you.

If you don't have uv yet:

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

## Install Arvel

**Add to your project:**

/// tab | uv
```bash
# From GitHub (available now)
uv add git+https://github.com/mohamed-rekiba/arvel@main

# From PyPI (once published)
uv add arvel
```
///

/// tab | pip
```bash
# From PyPI (once published)
pip install arvel
```
///

**Install the CLI as a standalone tool** (available globally without activating a venv):

/// tab | uv
```bash
# From GitHub (available now)
uv tool install --upgrade --force "git+https://github.com/mohamed-rekiba/arvel.git"

# From PyPI (once published)
uv tool install arvel
```
///

/// tab | pipx
```bash
# From PyPI (once published)
pipx install arvel
```
///

Confirm everything wired up correctly:

```bash
arvel --help
```

## Create a new project

The fastest path is the built-in scaffold. It pulls the starter template, renders it with your app name, writes a sensible `.env`, and (unless you opt out) runs `uv sync` and `git init`.

```bash
arvel new my-app
```

Without flags, the CLI walks you through an interactive stack selector. Pick a preset or choose each service individually:

```
? Choose your stack:
❯ Minimal    — sqlite, memory, sync, log, local, collection, memory
  Standard   — postgres, redis, redis, smtp, local, collection, memory
  Full       — postgres, redis, taskiq, smtp, s3, meilisearch, redis
  Custom     — choose each service individually
```

### Presets

Presets bundle common driver choices so you don't configure each service by hand:

| Preset | Database | Cache | Queue | Mail | Storage | Search | Broadcast |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **minimal** (default) | sqlite | memory | sync | log | local | collection | memory |
| **standard** | postgres | redis | redis | smtp | local | collection | memory |
| **full** | postgres | redis | taskiq | smtp | s3 | meilisearch | redis |

```bash
arvel new my-app --preset standard
```

### Service flags

Override any service individually. These work on their own or on top of a preset:

```bash
arvel new my-app --database postgres --cache redis --mail smtp
arvel new my-app --preset standard --search meilisearch
```

### Non-interactive mode

For CI or scripts, pass `--no-input` to skip prompts. Combine with `--preset` or individual flags:

```bash
arvel new my-app --no-input                           # uses minimal defaults
arvel new my-app --preset full --no-input             # uses full preset
arvel new my-app -d postgres --cache redis --no-input # explicit choices
```

### All options

| Flag | Short | Description |
| --- | --- | --- |
| `--database` | `-d` | Database driver: `sqlite`, `postgres`, `mysql` (default: `sqlite`) |
| `--cache` | | Cache driver: `memory`, `redis` (default: `memory`) |
| `--queue` | | Queue driver: `sync`, `redis`, `taskiq` (default: `sync`) |
| `--mail` | | Mail driver: `log`, `smtp` (default: `log`) |
| `--storage` | | Storage driver: `local`, `s3` (default: `local`) |
| `--search` | | Search driver: `collection`, `meilisearch`, `elasticsearch` (default: `collection`) |
| `--broadcast` | | Broadcast driver: `memory`, `redis`, `log`, `null` (default: `memory`) |
| `--preset` | `-p` | Stack preset: `minimal`, `standard`, `full` |
| `--template` | `-t` | Template name from the registry (default: `default`) |
| `--using` | | Custom template repo URL (bypasses the registry) |
| `--branch` | `-b` | Template repo branch or tag |
| `--force` | `-f` | Overwrite an existing directory |
| `--no-git` | | Skip `git init` |
| `--no-install` | | Skip `uv sync` |
| `--no-input` | | Skip interactive prompts |

Run `arvel new --help` for the latest options.

Once the command finishes, step into the project and start the server (next section).

## Optional dependencies

Core Arvel stays lean; drivers and integrations are **extras** you opt into. The `arvel new` scaffold auto-installs the right extras based on your service choices (for example, `--database postgres --cache redis` adds `arvel[pg,redis]` to your `pyproject.toml`). You can also install them manually:

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

Combine extras with commas inside the quotes:

/// tab | uv
```bash
# From GitHub
uv add "git+https://github.com/mohamed-rekiba/arvel@main[pg,redis,smtp]"

# From PyPI (once published)
uv add "arvel[pg,redis,smtp]"
```
///

/// tab | pip
```bash
# From PyPI (once published)
pip install "arvel[pg,redis,smtp]"
```
///

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
