# CLI Command Reference

<a name="introduction"></a>
## Introduction

Arvel ships an Artisan-style CLI (built on Typer). Run commands from your project root:

```bash
arvel <command> [arguments] [options]
arvel --help
arvel <command> --help
```

<a name="quick-start"></a>
### Quick start

```bash
# Scaffold a project (runs outside any existing app)
arvel new my-api --kit api
cd my-api

# Local dev loop
arvel migrate
arvel db:seed
arvel serve --reload

# Inspect what you built
arvel route:list
arvel about
```

Common one-liners you'll reach for daily:

| Goal | Command |
|---|---|
| Fresh DB + seed data | `arvel migrate:fresh --seed` |
| Run tests | `arvel test` or `arvel test tests/feature/test_posts.py -k create` |
| Open a REPL with the app booted | `arvel shell` (alias `tinker`) |
| Export the live OpenAPI spec | `arvel openapi:export -o docs/api/openapi.yaml` |
| Scaffold model + migration + factory | `arvel make:model Post -mf` |
| See what a config key resolves to | `arvel config:show database.default` |

> [!NOTE]
> Most commands need a project — they look for `bootstrap/app.py` in the current directory tree. The exceptions that run anywhere: `about`, `key:generate`, `new`, and any `make:*` command, plus `--help` / `--version`.

> [!NOTE]
> The CLI runs every command on **one** event loop that the entrypoint owns. In a custom command, don't call `asyncio.run()` inside your Typer callback — it nests on the running loop and crashes with "asyncio.run() cannot be called from a running event loop". Hand your coroutine to `arvel.console.schedule_async(...)` instead; the entrypoint awaits it on the same loop (and turns a `typer.Exit(code)` raised inside it into the process exit code). Commands that drive their own loop — `serve` (uvicorn), `shell` (IPython) — opt out with `owns_process = True`.

### Global install and the project virtualenv

You can install `arvel` globally (`uv tool install arvel`, `pipx install arvel`) and run it from anywhere inside a project — no need to activate the virtualenv first.

When you invoke a global `arvel` inside a project, it finds the project's `.venv` and re-execs itself onto that interpreter before running anything. From there the command runs with the **project-pinned** arvel and the project's installed extras — exactly as if you'd run `source .venv/bin/activate` first. So `arvel --version` from inside a project reports the project's version, not the global one.

The handoff is skipped (the current interpreter runs as-is) when:

- you're already on the project's `.venv` interpreter (activated, or running `.venv/bin/arvel` directly),
- there's no `.venv` at the project root,
- you're outside a project, or
- you set `ARVEL_NO_REEXEC=1` to opt out.

If the project's `.venv` doesn't have arvel installed, the handoff is skipped and the command runs on the current interpreter (which will report a clear import error). Install the project's deps (`uv pip install -e .`) to fix it.

### Needs-based bootstrap

Every command declares which **subsystems** it touches (`Command.requires`). The CLI computes the transitive closure of those subsystems and asks the user's `bootstrap/app.py::create_application(required_subsystems=...)` to boot only those providers. The four foundation subsystems — `CONFIG`, `LOG`, `LANG`, `CONTEXT` — are always loaded; everything else (`DATABASE`, `HTTP`, `QUEUE`, `MAIL`, `CACHE`, `STORAGE`, `BROADCAST`, `AUTH`, `EVENTS`, `SCHEDULER`, `USER_PROVIDERS`) only boots when something asks for it.

In practice this means:

- `arvel make:controller Foo` boots nothing — no database, no HTTP stack, no user providers.
- `arvel migrate` boots `Database` plus foundation. No queue, no mail, no scheduler.
- `arvel queue:work` boots `Queue → Database` plus the user's `bootstrap/providers.py` (`USER_PROVIDERS`) so your custom jobs are registered.
- `arvel openapi:export` boots `HTTP` plus `USER_PROVIDERS` so every registered route appears in the spec.

Plug-in commands (`auth:install`, `oauth:install`, `audit:install`, `reverb:start`) only register when their provider is in the closure. `--help` outside of a project still works because no closure is computed.

Some commands only register when their provider is installed: most `queue:*` commands need `QueueServiceProvider` (`queue:restart` is always available, but `queue:clear` and `queue:prune-failed` still need a booted app with the queue manager bound), `auth:install` needs `AuthServiceProvider`, and `reverb:start` needs the `[broadcasting]` extra.

<a name="custom-commands"></a>
## Writing Custom Commands

Generate a stub:

```bash
arvel make:command SendWeeklyReport
# → app/console/commands/send_weekly_report.py  (name: send:weekly:report)
```

A minimal command implements `handle()` and returns an exit code (`0` = success):

```python
from typing import ClassVar

from arvel.console import Command, Context


class SendWeeklyReportCommand(Command):
    name: ClassVar[str] = "report:weekly"
    help: ClassVar[str] = "Email the weekly digest"

    def handle(self, ctx: Context) -> int:
        ctx.info("Queued weekly report.")
        return 0
```

Commands are discovered from `app/console/commands/` and from any provider's `commands()` hook (see [Service Providers](../core-concepts/service-providers.md)).

### Typed flags — override `register()`

When the command needs arguments or options, override `register()` and wire Typer directly (same pattern as `migrate` and `make:model`):

```python
from typing import Annotated, ClassVar

import typer

from arvel.console import Command, Context
from arvel.console._t import Argument as _Argument
from arvel.console._t import Option as _Option


class GreetCommand(Command):
    name: ClassVar[str] = "greet"
    help: ClassVar[str] = "Say hello"

    def register(self, app: typer.Typer) -> None:
        cmd_self = self

        def _callback(
            name: Annotated[str, _Argument(help="Who to greet")],
            *,
            loud: Annotated[bool, _Option("--loud", help="SHOUT")] = False,
        ) -> None:
            ctx = Context()
            message = f"Hello, {name}!"
            if loud:
                message = message.upper()
            ctx.info(message)

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError
```

```bash
arvel greet Alice
arvel greet Alice --loud
```

### Async work — use `schedule_async`

Database, cache, queue, and most I/O commands run on the CLI's single event loop. **Don't** call `asyncio.run()` inside a Typer callback — nest it on the running loop and crash. Schedule your coroutine instead:

```python
from typing import ClassVar

import typer

from arvel.console import Command, Context
from arvel.console import schedule_async
from arvel.console._subsystem import CliSubsystem


class PurgeStaleCommand(Command):
    name: ClassVar[str] = "purge:stale"
    help: ClassVar[str] = "Delete expired rows"
    requires: ClassVar[frozenset[CliSubsystem]] = frozenset({CliSubsystem.DATABASE})

    def register(self, app: typer.Typer) -> None:
        cmd_self = self

        def _callback() -> None:
            schedule_async(cmd_self._run())

        app.command(name=self.name, help=self.help)(_callback)

    async def _run(self) -> None:
        from sqlalchemy.ext.asyncio import AsyncSession

        session = self.app.container.make(AsyncSession)
        async with session:
            # await YourModel.query().where(...).delete()
            typer.echo("Purged.")

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError
```

The entrypoint awaits the scheduled coroutine after Typer returns. A `typer.Exit(code=…)` raised inside it becomes the process exit code.

Commands that manage their own loop (`serve`, `shell`) set `owns_process = True` so the entrypoint skips the shared loop wrapper.

### Framework DI — declare `requires`

List the subsystems your command touches on `requires`. The entrypoint boots only those providers and binds `self.app`:

```python
from arvel.console._subsystem import CliSubsystem

requires: ClassVar[frozenset[CliSubsystem]] = frozenset({
    CliSubsystem.DATABASE,
    CliSubsystem.QUEUE,
})
```

`QUEUE` pulls in `DATABASE` transitively. Foundation subsystems (`CONFIG`, `LOG`, `LANG`, `CONTEXT`) always load. Leave `requires` empty for pure generators (`make:*`, `new`) — they skip provider boot entirely.

Resolve services from the container inside `handle()` or your async body:

```python
from arvel.facades.cache import Cache

async def _run(self) -> None:
    await Cache.forget("dashboard:stats")
```

### Calling other commands in-process

When `self.app` is bound, chain commands without spawning a subprocess. `call` /
`call_silently` are async and dispatch through the target's real Typer callback,
so you can pass flags and the target's async work runs (not a stub `handle()`).
Defer your composite body the same way any async command does:

```python
def register(self, app: typer.Typer) -> None:
    cmd_self = self

    def _callback() -> None:
        schedule_async(cmd_self._run())

    app.command(name=self.name, help=self.help)(_callback)

async def _run(self) -> int:
    code = await self.call("migrate", "--dry-run")
    if code != 0:
        return code
    return await self.call_silently("db:seed")
```

Extra positional args become CLI tokens on the target — `self.call("migrate", "--dry-run")`
parses exactly like `arvel migrate --dry-run`.

<a name="top-level"></a>
## Top-Level Commands

| Command | Description | Key options |
|---|---|---|
| `new NAME` | Scaffold a new project from the skeleton | `--no-install`, `--python`, `--kit` (default `api`) |

```bash
arvel new blog --kit api          # API skeleton (default)
arvel new shop --kit ecommerce    # E-commerce kit — see [E-commerce Kit](../kits/ecommerce-kit.md)
arvel new demo --no-install       # Skip `uv sync`; install deps yourself
```
| `serve` | Run the app under uvicorn | `--host` (`127.0.0.1`), `--port` (`8000`), `--workers`, `--reload` |
| `about` | Print framework info | — |
| `shell` | Interactive REPL with the app booted | `--dry-run` |
| `tinker` | Alias for `shell` | (same as `shell`) |
| `test [args...]` | Run pytest; extra args forwarded | — |
| `down` | Enter maintenance mode | `--secret`, `--retry`, `--refresh`, `--render` |
| `up` | Exit maintenance mode | — |
| `migrate` | Run pending migrations | `--dry-run` |
| `optimize` | Pre-compile config + view caches | — |
| `optimize:clear` | Remove config + view caches | — |

> [!NOTE]
> `optimize` builds the config and view caches only. It prints that route/event caching is pending — there are no `route:cache` or `event:cache` commands yet.

> [!NOTE]
> `shell` / `tinker` connect to the database **lazily**, like Laravel Tinker — the REPL opens even when the DB is unreachable, and a connection error only surfaces on your first query. Servers and DB-using commands (`serve`, `migrate`, …) still fail fast at boot if the database is down.

<a name="make"></a>
## `make:` Scaffolding

Every `make:*` command takes a class `name` and supports `--force` to overwrite.

| Command | Generates | Extra options |
|---|---|---|
| `make:controller` | HTTP controller | `--resource`, `--api` (needs `--resource`), `--model`, `--model-name`, `--observer`, `--policy`, `--requests` |
| `make:model` | ORM model | `--view`, `--materialized-view`; companions: `--migration`/`-m`, `--factory`/`-f`, `--seed`/`-s`, `--controller`/`-c` (`--resource`, `--api`), `--requests`, `--policy`/`-p`, `--observer`/`-o`, `--json-resource`/`-R`, `--test`, `--all`/`-a` |
| `make:migration` | Migration file | `--view`, `--materialized-view`, `--extension` |
| `make:request` | Typed `FormRequest` | — |
| `make:resource` | `JsonResource` transformer | — |
| `make:schema` | Pydantic Create/Update/Read schemas from a model | — |
| `make:service` | Application service class | — |
| `make:job` | Queued `Job` | — |
| `make:event` | Event class | — |
| `make:listener` | Event listener | — |
| `make:notification` | Notification | — |
| `make:mail` | Mailable | — |
| `make:middleware` | HTTP middleware | — |
| `make:policy` | Authorization policy | — |
| `make:provider` | Service provider | — |
| `make:seeder` | Database seeder | — |
| `make:factory` | Model factory | — |
| `make:test` | Feature test | — |
| `make:command` | Console command | — |
| `make:cast` | Custom column cast | — |
| `make:observer` | Model observer | — |
| `make:channel` | Broadcast channel auth callback | — |
| `make:view` | Jinja template | — |

Companion flags on `make:model` stack — generate the whole vertical slice in one shot:

```bash
arvel make:model Article -mfcsR --all   # model + migration + factory + controller + JsonResource + …
arvel make:controller Post --resource --requests --policy
arvel make:migration add_status_to_posts --table=posts
```

<a name="migrate"></a>
## `migrate:` Schema Migrations

| Command | Description | Options |
|---|---|---|
| `migrate:rollback` | Roll back the last batch | — |
| `migrate:status` | Show migration status | — |
| `migrate:reset` | Roll back every migration | — |
| `migrate:refresh` | Reset, then re-run all | `--seed`, `--seeder` |
| `migrate:fresh` | Drop all tables, re-run all | `--seed`, `--seeder` |

> [!WARNING]
> `migrate:fresh` and `migrate:refresh` are destructive. In production they refuse to run unless `ARVEL_ALLOW_DESTRUCTIVE=1` is set.

Exit codes for migration commands:

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Migration body failed (bad file, SQL error) |
| `2` | Bootstrap failed or database unreachable |

Preview pending migrations without applying:

```bash
arvel migrate --dry-run
arvel migrate:status
```

<a name="db"></a>
## `db:` Database

| Command | Description | Options |
|---|---|---|
| `db:seed` | Run seeders | `--seeder` (default `DatabaseSeeder`) |
| `db:show` | Print connection + table summary | — |
| `db:table TABLE` | Print a table's columns and indexes | — |

```bash
arvel db:show
arvel db:table users
arvel db:seed --seeder=DemoSeeder
```

<a name="model"></a>
## `model:` Models

| Command | Description |
|---|---|
| `model:show PATH` | Print model metadata (e.g. `model:show app.models.User`) |
| `model:prune` | Delete stale rows for all `Prunable` models |

```bash
arvel model:show app.models.User
arvel model:prune   # runs Model.prune() on every Prunable model
```

<a name="config"></a>
## `config:` Configuration

| Command | Description | Options |
|---|---|---|
| `config:show KEY` | Print a resolved dotted value (e.g. `app.name`) | — |
| `config:publish` | Publish package config into the app | `--provider`, `--tag`, `--force` |
| `config:cache` | Serialize config to `bootstrap/cache/config.json` | — |
| `config:clear` | Delete the cached config file | — |

Production boot reads `bootstrap/cache/config.json` when present — build it after changing `config/*.py`:

```bash
arvel config:cache
arvel config:show app.debug
arvel vendor:publish --provider=SomePackageProvider --tag=config
```

<a name="cache"></a>
## `cache:` Cache

| Command | Description | Options |
|---|---|---|
| `cache:clear` | Flush the cache | `--store` / `-s` |
| `cache:forget KEY` | Remove one key | `--store` / `-s` |

<a name="queue"></a>
## `queue:` Queues

| Command | Description | Options |
|---|---|---|
| `queue:work` | Start a worker | `--queue` (`default`), `--stop-when-empty` |
| `queue:size` | Count pending jobs | `--queue` (`default`) |
| `queue:failed` | List failed jobs | `--queue` (filter) |
| `queue:retry` | Re-dispatch a failed job | `uuid`, or `--all` |
| `queue:forget UUID` | Delete one failed job | — |
| `queue:flush` | Delete all failed jobs | — |
| `queue:prune-failed` | Delete failed jobs older than a threshold | `--hours` (`24`) |
| `queue:clear` | Remove pending jobs from a queue | `--queue` (`default`), `--connection` |
| `queue:restart` | Signal workers to restart gracefully | — |

Typical worker loop:

```bash
arvel queue:work --queue=default,emails
arvel queue:failed
arvel queue:retry --all
arvel queue:restart   # graceful reload after deploy (workers pick this up)
```

<a name="schedule"></a>
## `schedule:` Task Scheduler

| Command | Description | Options |
|---|---|---|
| `schedule:work` | Run the scheduler loop (foreground) | `--once`, `--sleep` (`60`), `--max-failures` |
| `schedule:run` | Run due tasks once (alias for `schedule:work --once`) | — |
| `schedule:list` | List registered tasks | — |
| `schedule:interrupt` | Stop the scheduler at the next tick | — |
| `schedule:pause` | Pause dispatching | — |
| `schedule:continue` | Resume dispatching | — |

Cron-style one-shot (what you'd put in crontab):

```bash
arvel schedule:run
```

Long-running scheduler process:

```bash
arvel schedule:work --sleep=60
arvel schedule:list
```

<a name="route"></a>
## `route:` Routing

| Command | Description | Options |
|---|---|---|
| `route:list` | List registered routes | `--filter` (path substring), `--json` |

<a name="view"></a>
## `view:` Views

| Command | Description |
|---|---|
| `view:cache` | Pre-compile Jinja templates |
| `view:clear` | Clear the compiled view cache |

<a name="storage"></a>
## `storage:` File Storage

| Command | Description | Options |
|---|---|---|
| `storage:link` | Symlink `public/storage` → `storage/app/public`; the framework then serves it at `/storage` | `--relative` |
| `storage:unlink` | Remove the symlink (idempotent) | — |

After `storage:link`, restart the app: it mounts `public/storage` as static files at `/storage`,
so linked files are retrievable with no reverse proxy. See [Storage → Serving Local Files](../features/storage.md#serving-local-files).

<a name="auth"></a>
## `auth:` Authentication

| Command | Description | Options |
|---|---|---|
| `auth:install` | Publish auth scaffolding (config, routes, views, migrations) | `--force` |
| `auth:clear-resets` | Delete expired password-reset tokens | — |

<a name="key"></a>
## `key:` Application Key

| Command | Description | Options |
|---|---|---|
| `key:generate` | Generate `APP_KEY` and write to `.env` | `--show`, `--force` |
| `key:rotate` | Re-encrypt encrypted columns with a new key | `--old-key`, `--new-key`, `--force` |

<a name="openapi"></a>
## `openapi:` API Spec

| Command | Description | Options |
|---|---|---|
| `openapi:export` | Export the OpenAPI spec to a file | `--output` / `-o` (`docs/api/openapi.yaml`; absolute paths allowed; `-` = stdout), `--format` / `-f` (`yaml`\|`json`), `--stdout` |
| `openapi:validate` | Validate a spec against OpenAPI 3.x | `--spec` (defaults to the live app spec) |

`--output` accepts any path the calling user can write to: absolute (`/tmp/spec.yaml`), sibling (`../frontend/openapi.yaml`), or POSIX `-` for stdout (equivalent to `--stdout`). Relative paths resolve against the current working directory — the same rule `git`, `make`, and `cp` use, not the project root. Parent directories are created on demand. Status messages (`OpenAPI spec written to ...`) go to **stderr** so you can pipe stdout into another tool:

```bash
arvel openapi:export --output - --format json | jq '.info'
arvel openapi:export --stdout > captured.yaml
arvel openapi:export --output ../frontend/openapi.yaml --no-banner
```

<a name="events"></a>
## `channel:` / `event:` / `reverb:` Events & Broadcasting

| Command | Description | Options |
|---|---|---|
| `channel:list` | List broadcast channels | — |
| `event:list` | List events and their listeners | — |
| `reverb:start` | Start the Reverb WebSocket server | `--host`, `--port` |

<a name="vendor"></a>
## `vendor:` Package Assets

| Command | Description | Options |
|---|---|---|
| `vendor:publish` | Publish package files (migrations, config, assets) | `--provider`, `--tag`, `--force` |

Companion packages add their own `vendor:publish` tags — for example `arvel vendor:publish --tag=arvel-image`. See [Companion packages](../packages/README.md).
