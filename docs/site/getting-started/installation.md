# Installation

<a name="meet-arvel"></a>
## Meet Arvel

Arvel is a web application framework with expressive, elegant syntax. A framework provides a starting point and structure so you can focus on building something amazing while it sweats the details.

Arvel strives to provide an outstanding developer experience while delivering powerful features: a full-featured async ORM, a fluent router, a service container, a CLI, queues, caching, and much more. If you know Laravel, you'll feel right at home — Arvel borrows its shape and conventions, recast for modern async Python.

<a name="quick-start"></a>
### Quick start

```bash
uv tool install arvel
arvel new my-app
cd my-app
arvel key:generate
uv run arvel serve --reload
curl http://127.0.0.1:8000/api/healthz
```

Then follow the [Quickstart](quickstart.md) to add a model and your first data endpoint.

<a name="prerequisites"></a>
## Prerequisites

- **Python 3.14+**. Check with `python --version`.
- A package manager. These docs use [`uv`](https://docs.astral.sh/uv/); `pipx` and `pip` also work.

<a name="installing-the-cli"></a>
## Installing the CLI

Install `arvel` as a global tool:

```bash
uv tool install arvel
# or
pipx install arvel
```

Verify it:

```bash
arvel about
```

<a name="creating-a-project"></a>
## Creating a Project

```bash
arvel new my-app
cd my-app
```

`arvel new` scaffolds a Laravel-shaped project from the packaged skeleton and installs dependencies. Useful flags:

| Flag | Effect |
|---|---|
| `--no-install` | Skip dependency installation |
| `--python <version>` | Pin the project to a Python version constraint (e.g. `3.14`) |
| `--kit <name>` | Choose a starter kit. Default: `api` |

> [!NOTE]
> `arvel new`, every `make:*` generator, `about`, and `key:generate` work **outside** a project. All other commands require a project directory — one that contains `bootstrap/app.py`. See the [CLI reference](../cli/commands.md).

<a name="the-development-server"></a>
## The Development Server

```bash
uv run arvel serve --reload
```

This serves the ASGI app at `public.asgi:asgi` on `http://127.0.0.1:8000` by default. Open `http://127.0.0.1:8000/api/healthz`:

```json
{"status": "ok"}
```

`serve` accepts `--host` (default `127.0.0.1`), `--port` (default `8000`), `--workers`, and `--reload`. The interactive OpenAPI docs are served by FastAPI at `http://127.0.0.1:8000/docs`.

<a name="the-application-key"></a>
## The Application Key

Encryption, signed URLs, and encrypted cookie sessions need an `APP_KEY`:

```bash
arvel key:generate
```

This writes a base64 key to `.env`. See [Encryption](../features/encryption.md).

<a name="optional-extras"></a>
## Optional Extras

Arvel ships a slim core. Install drivers and integrations as you need them:

```bash
uv add "arvel[all]"          # everything
uv add "arvel[redis]"        # Redis cache / sessions / queue
uv add "arvel[postgres]"     # asyncpg + psycopg
uv add "arvel[sqlite]"       # aiosqlite
uv add "arvel[jwt]"          # JWT guard
uv add "arvel[mail]"         # SMTP mail driver
uv add "arvel[queue]"        # Taskiq broker
uv add "arvel[s3]"           # S3 storage
uv add "arvel[azure]"        # Azure Blob storage
uv add "arvel[gcs]"          # Google Cloud Storage
uv add "arvel[broadcasting]" # Reverb WebSocket server
```

> [!NOTE]
> The exact extras available are defined in the framework's `pyproject.toml`. If an extra you expect is missing, check there.

<a name="next-steps"></a>
## Next Steps

- [Quickstart](quickstart.md) — build your first route, model, and migration.
- [Project structure](project-structure.md) — learn where everything lives.
