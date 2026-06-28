# Console

Not everything happens over HTTP. You need to run migrations, scaffold a model, kick off a one-off
backfill, tick a scheduler, or give an operator a safe button to push. arvel ships a CLI — the
`arvel` command, built on [Typer](https://typer.tiangolo.com) — for exactly that: it scaffolds code,
runs migrations and seeders, drives the scheduler, and hosts **your own** commands, all with typed
options and generated `--help`.

This page covers running commands, the built-in set, the code generators, scheduling and seeding,
and writing your own command. The console is part of the **core** — nothing to install.

## Running commands

```bash
arvel --help            # the full command tree
arvel route:list        # every registered route
arvel migrate           # apply outstanding migrations
```

Commands are **lazily loaded**: invoking one imports only that command's module, so cold-start
stays fast and the bare `arvel` / `--version` paths pull in no framework or DB code.

## One binary, two modes

The same `arvel` works *before* a project exists and *inside* one — it tells which by looking for
`bootstrap/app.py`:

| Mode | Where | Shows |
|------|-------|-------|
| **Installer** | anywhere, no project | `arvel new …` (+ `about`, `extras`) |
| **Project** | inside a project | `migrate`, `queue:work`, `make:*`, `tinker`, `route:list`, … |

So `arvel new blog` works from an empty directory, then inside `blog/` the full command set
appears. (No separate installer binary — one tool, like `git`.)

## The built-in commands

| Command | What it does |
|---------|--------------|
| `make:model <Name>` | scaffold a model |
| `make:controller <Name>` | scaffold a controller |
| `make:middleware <Name>` | scaffold a middleware class |
| `make:request <Name>` | scaffold a Form Request |
| `make:job <Name>` | scaffold a queued job |
| `make:policy <Name>` | scaffold an authorization policy |
| `make:notification <Name>` | scaffold a notification |
| `make:mail <Name>` | scaffold a mailable |
| `make:rule <Name>` | scaffold a validation rule |
| `make:seeder <Name>` | scaffold a database seeder |
| `make:factory <Name>` | scaffold a model factory |
| `make:provider <Name>` | scaffold a service provider |
| `make:migration <name>` | scaffold a timestamped migration (`create_x_table` → create stub) |
| `make:command <Name>` | scaffold a console command (register it in a provider's `commands()`) |
| `route:list` | tabulate the app's routes (methods, path, name) |
| `migrate` / `migrate:rollback` | apply / revert migrations |
| `db:seed` | run the app's database seeder |
| `schedule:run` | run scheduled tasks that are due now |
| `lang:list` | list available locales |
| `queue:work` | run a worker that processes queued jobs |
| `package:discover` | cache the ecosystem-package manifest to `bootstrap/cache/packages.py` |
| `tinker` | an interactive REPL with the app booted, your models autoloaded, and top-level `await` |

## The REPL (`tinker`)

`tinker` drops you into an interactive shell with the app booted. On **IPython** (shipped with
`arvel[standard]`, or `uv add 'arvel[console]'`) you get **top-level `await`** and autocomplete; without
it, it falls back to the stdlib REPL (no `await`). Inside a project it preloads:

- arvel's public surface (`Model`, `config`, `Collection`, …),
- the running `app`,
- **every model by its short name** (autoloaded from `app/models/`, Laravel-Tinker style).

```python
arvel tinker
>>> await User.find(1)          # top-level await — no asyncio.run needed
>>> Post.query().where(...)     # models reachable by name, no import
```

## Generators

`make:*` commands write a typed stub into the right `app/` package:

```bash
arvel make:model Post
arvel make:controller PostController
arvel make:request StorePostRequest
```

Each generates a version-matched file you then fill in — no boilerplate copied by hand.

## Scheduling

Define recurring work in `routes/console.py` with the `Schedule` facade, then let `schedule:run`
(driven by a once-a-minute cron entry) fire what's due:

```python
# routes/console.py
from arvel import Schedule

Schedule.call(prune_tokens).daily_at("02:00")
Schedule.job(GenerateReport()).hourly()
Schedule.command("cache:prune-stale").cron("*/15 * * * *").on_one_server()
```

```bash
* * * * *  cd /app && arvel schedule:run >> /dev/null 2>&1
```

`schedule:run` resolves the app's bound `schedule`, runs the events whose cron expression
matches the current minute, and reports how many ran.

## Seeding

A `Seeder` inserts development/test data; `db:seed` runs your root seeder:

```python
from arvel.database import Seeder

class DatabaseSeeder(Seeder):
    async def run(self):
        await self.call(UserSeeder, PostSeeder)   # chain child seeders

class UserSeeder(Seeder):
    async def run(self):
        await User.create(name="Ada", email="ada@example.com")
```

```bash
arvel db:seed
```

## Writing your own command

A command is a small Typer app the framework discovers and mounts under `arvel`:

```python
import typer
from arvel.database import Model

publish_app = typer.Typer()

@publish_app.command()
def publish_posts(limit: int = 10) -> None:
    """Publish up to LIMIT scheduled posts."""
    import asyncio
    asyncio.run(_publish(limit))
    typer.echo(f"published up to {limit} post(s)")
```

Typer generates `--help` and parses `--limit` as an `int` automatically. Class commands are
resolved through the container, so their constructor dependencies are injected.

## Common mistakes & gotchas

- **Importing heavy modules at the top of a command file.** The CLI stays fast because command
  modules are lazy — keep DB/HTTP imports *inside* the command function so `arvel --version`
  and `make:*` don't pull them in (the import-linter enforces this for the framework).
- **`schedule:run` with nothing bound.** It exits non-zero with a message if no `schedule` is
  registered — wire one in `routes/console.py`.
- **Expecting `migrate` to discover migrations magically.** It runs the `migrations` the app
  has bound; register them so the command can find them.

## How it works

The root `arvel` app is a Typer with a `LazyGroup`: a manifest maps command names
(`route:list`, `migrate:rollback`, …) to `module:typer_app` targets, and the target module is
imported only when that command is invoked. Commands resolve the booted application from the
container (`route:list` → the router, `migrate` → the bound migrator), so the pure formatters
stay unit-testable while the command wires in the live app.

## See also

- [Queues & Jobs](queues.md) — the scheduler dispatches jobs.
- [Database & ORM](database/index.md) — what `migrate`/`db:seed` operate on.
