# CLI Command Reference

<a name="introduction"></a>
## Introduction

Arvel ships an Artisan-style CLI (built on Typer). Run commands from your project root:

```bash
arvel <command> [arguments] [options]
arvel --help
arvel <command> --help
```

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

<a name="top-level"></a>
## Top-Level Commands

| Command | Description | Key options |
|---|---|---|
| `new NAME` | Scaffold a new project from the skeleton | `--no-install`, `--python`, `--kit` (default `api`) |
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

<a name="make"></a>
## `make:` Scaffolding

Every `make:*` command takes a class `name` and supports `--force` to overwrite.

| Command | Generates | Extra options |
|---|---|---|
| `make:controller` | HTTP controller | `--resource`, `--api` (with `--resource`), `--model` (with `--resource`) |
| `make:model` | ORM model | `--view`, `--materialized-view` |
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

<a name="db"></a>
## `db:` Database

| Command | Description | Options |
|---|---|---|
| `db:seed` | Run seeders | `--seeder` (default `DatabaseSeeder`) |
| `db:show` | Print connection + table summary | — |
| `db:table TABLE` | Print a table's columns and indexes | — |

<a name="model"></a>
## `model:` Models

| Command | Description |
|---|---|
| `model:show PATH` | Print model metadata (e.g. `model:show app.models.User`) |
| `model:prune` | Delete stale rows for all `Prunable` models |

<a name="config"></a>
## `config:` Configuration

| Command | Description | Options |
|---|---|---|
| `config:show KEY` | Print a resolved dotted value (e.g. `app.name`) | — |
| `config:publish` | Publish package config into the app | `--provider`, `--tag`, `--force` |
| `config:cache` | Serialize config to `bootstrap/cache/config.json` | — |
| `config:clear` | Delete the cached config file | — |

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
