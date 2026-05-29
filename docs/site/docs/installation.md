# Installation

Arvel is a Python web framework built on FastAPI + Pydantic + SQLAlchemy, end-to-end typed. This page goes from a clean machine to a running app.

If you already have Python 3.14+ and [uv](https://docs.astral.sh/uv/), skip straight to [Creating an Application](#creating-an-application).

## Creating an Arvel Application

### Getting started using AI

If you are using an AI coding agent like [Cursor](https://cursor.com) or [Claude Code](https://docs.anthropic.com/en/docs/claude-code), you can start with a prompt that gives the agent an Arvel-specific playbook before it touches your project:

```text
I'm building a new Arvel application.

Fetch and follow the instructions from https://docs.arvel.dev/getting-started/installation. Treat the returned Markdown as the source of truth for how to install and set up Arvel in this session.
```

After the agent reads the instructions, it should guide you step by step and keep the setup aligned with Arvel's defaults.

### Installing Python and uv

Before creating your first Arvel application, make sure your local machine has [Python 3.14+](https://www.python.org/downloads/) and [uv](https://docs.astral.sh/uv/getting-started/installation/) installed.

=== "macOS / Linux"

    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    uv python install 3.14
    ```

=== "Windows PowerShell"

    ```powershell
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    uv python install 3.14
    ```

=== "Homebrew"

    ```bash
    brew install uv
    uv python install 3.14
    ```

### Creating an application

The fastest way to bootstrap a new Arvel project is the `arvel` CLI:

```bash
uv tool install arvel
arvel new my-app
cd my-app
```

`arvel new` writes a typed project skeleton with the canonical Arvel layout (config, routes, providers, ORM, tests).

Once the application has been created, you can install dependencies and start the local development server:

```bash
uv sync
uv run uvicorn app:create_app --factory --reload
```

Open <http://localhost:8000> in your browser. You should see Arvel's welcome page.

## Initial Configuration

All Arvel configuration is **typed** — every config object is a Pydantic `BaseSettings` subclass registered with the framework. Environment variables are read at boot, validated against the schema, and exposed via the `Config` facade.

```python
from pydantic import SecretStr
from arvel.config import ArvelSettings, register
from arvel.facades import Config


@register
class DbConfig(ArvelSettings):
    url: str = "postgresql+asyncpg://localhost/app"
    password: SecretStr = SecretStr("")
    # env_prefix auto-derived: "DB_"; reads DB_URL, DB_PASSWORD


db = Config.of(DbConfig)
```

See [Configuration](configuration.md) for the full guide.

### Environment-based configuration

Arvel reads environment variables from your shell, your `.env` file at the project root, and your process manager (`uvicorn`, `gunicorn`, `systemd`, `kubernetes`) — in that order of precedence.

Your `.env` file should **not** be committed to version control. Different developers and different environments will require different values, and committing secrets to a public repository would be a security incident.

### Databases and migrations

By default, an Arvel application created via `arvel new` is configured to use SQLite. The installer creates a `database/database.sqlite` file for you and runs the initial migrations.

If you prefer Postgres or MySQL, update the `DB_URL` variable in your `.env`:

```env
DB_URL=postgresql+asyncpg://user:pass@127.0.0.1:5432/myapp
```

Then run the migrations:

```bash
uv run arvel migrate
```

See [Migrations](migrations.md) for the full guide.

## Optional extras

Arvel ships with a slim core. Pull in extras only for the subsystems you use:

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

## IDE support

Because Arvel is strictly typed end to end, you get **real** auto-complete and type checking — not lies. Both [PyCharm](https://www.jetbrains.com/pycharm/) and [VS Code](https://code.visualstudio.com/) (with the Pylance / Pyright extension) work out of the box. Cursor pairs especially well with Arvel's convention-driven structure.

## Next steps

- New here? Read [Configuration](configuration.md) to set up your `.env` file.
- Coming from Laravel? Skim [Directory Structure](structure.md) — the conventions transfer.
- Building an API? Jump to [Routing](routing.md) and [Validation](validation.md).
- Building a CRUD app? See the [ORM](arvent.md) and [Migrations](migrations.md).
