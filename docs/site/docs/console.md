# Console

Arvel's console is built on **Typer** — every framework command is a typed Python function. The CLI entry point is `arvel`. Scaffolding a new project uses the same binary: `arvel new <name>`.

## Available commands

Run `arvel --help` for the full list. Here's the catalog grouped by purpose:

### Scaffolding (`make:*`)

Class generators write Python stubs that target Arvel's stack (Pydantic
models, async listeners, type-safe policies, etc.). All accept `--force`
to overwrite an existing file.

```bash
arvel make:cast <Name>           # app/casts/<Name>.py (SQLAlchemy TypeDecorator)
arvel make:channel <Name>        # app/broadcasting/channels/<Name>.py (auth callback)
arvel make:command <Name>        # app/console/commands/<Name>.py (arvel.Command)
arvel make:controller <Name>     # app/http/controllers/<Name>.py (arvel.Controller)
arvel make:event <Name>          # app/events/<Name>.py (Pydantic Event)
arvel make:factory <Name>        # database/factories/<Name>.py (Factory[Model] + definition)
arvel make:job <Name>            # app/jobs/<Name>.py (Pydantic Job + handle())
arvel make:listener <Name>       # app/listeners/<Name>.py (Listener[E] + handle())
arvel make:mail <Name>           # app/mail/<Name>.py (Mailable: envelope/content)
arvel make:middleware <Name>     # app/http/middleware/<Name>.py (handle + call_next)
arvel make:model <Name>          # app/models/<Name>.py (SQLAlchemy Model + Timestamps)
arvel make:notification <Name>   # app/notifications/<Name>.py (via + to_*)
arvel make:observer <Name>       # app/observers/<Name>.py (lifecycle hooks)
arvel make:policy <Name>         # app/policies/<Name>.py (async Policy[T])
arvel make:provider <Name>       # app/providers/<Name>.py (register/boot/commands)
arvel make:request <Name>        # app/http/requests/<Name>.py (FormRequest[Payload])
arvel make:resource <Name>       # app/http/resources/<Name>.py (JsonResource[T])
arvel make:schema <Name>         # app/schemas/<Name>.py (Pydantic Read/Create/Update from Model)
arvel make:service <Name>        # app/services/<Name>.py
arvel make:test <Name>           # tests/feature/<Name>.py (pytest + TestClient)
arvel make:view <Name>           # resources/views/<Name>.html.jinja (extends layouts/base.html)
```

Every class-based generator normalizes the input — `make:mail welcome_mail`,
`make:mail WelcomeMail`, and `make:mail welcomeMail` all produce
`class WelcomeMail`. The generated file name mirrors the input as-is.

`make:controller` accepts three resource-flavoured switches that mirror
`Route.resource()` (see [controllers](controllers.md#resource-controllers)):

```bash
arvel make:controller PostController --resource              # 7 RESTful method stubs
arvel make:controller PostController --resource --api        # drops create()/edit()
arvel make:controller PostController --resource --model=Post # imports Post + types member params
```

`--api` and `--model` both require `--resource`. The generated stubs raise
`NotImplementedError` and pass `ruff` and `mypy --strict` immediately.

Migration generators write a `database/migrations/<timestamp>_<name>.py`
file with the standard `async def up(schema)` / `async def down(schema)`
hooks.

```bash
arvel make:migration <Name>                # table migration (Blueprint + Schema.create)
arvel make:migration --view <Name>         # view migration (Schema.create_view)
arvel make:migration --materialized-view <Name>  # materialized view (PostgreSQL only)
arvel make:migration --extension <Name>    # extension install migration (PostgreSQL only)
arvel make:seeder <Name>                   # database/seeders/<Name>.py
```

`--view`, `--materialized-view`, and `--extension` are mutually exclusive. See [Migrations](migrations.md) for
generated stub examples and the name-inference rules.

Migrations for Arvel's built-in subsystems (auth, sessions, cache, queue,
notifications, identity) ship as **publishable stubs** on each subsystem's
service provider. Stamp them into your app with `vendor:publish`:

```bash
arvel vendor:publish --tag=arvel-auth          # users + refresh tokens + PATs
arvel vendor:publish --tag=arvel-session       # sessions
arvel vendor:publish --tag=arvel-cache         # cache
arvel vendor:publish --tag=arvel-queue         # jobs + failed_jobs
arvel vendor:publish --tag=arvel-notifications # notifications
arvel vendor:publish --tag=arvel-permission    # roles + permissions (5 tables)
```

`vendor:publish` copies each registered file into your app, rewriting
migration filenames with a current UTC timestamp so they run in the right
order. Filter by `--provider <ClassName>` instead of `--tag` if a provider
ships multiple groups, and pass `--force` to overwrite existing files.

Names accept simple nested namespacing with `/`
(e.g. `Billing/SendInvoice`), which is normalized to `os.sep`. The
generator rejects names containing path traversal, shell metacharacters,
null bytes, or fullwidth/zero-width characters.

### Migrations

```bash
arvel migrate                    # apply pending migrations
arvel migrate --dry-run          # print what would run, don't apply
arvel migrate:rollback           # roll back the most recent batch
arvel migrate:status             # applied/pending status table
arvel migrate:fresh              # drop ALL tables (including untracked), re-apply every migration
arvel migrate:fresh --seed       # ...and run database/seeders/database_seeder.py after
arvel migrate:reset              # roll back every tracked migration via downgrade()
arvel migrate:refresh            # downgrade every migration then upgrade — verifies rollback paths
arvel migrate:refresh --seed     # ...and seed after
```

`migrate:fresh` drops every table in the database regardless of whether the
migrator tracks it — useful for a completely clean local slate. `migrate:refresh`
runs each migration's `downgrade()` then `upgrade()` in sequence — it respects
migration history and is the right tool for verifying your rollback logic works.

`migrate:fresh`, `migrate:reset`, and `migrate:refresh` are destructive.
They exit `2` without doing anything when `app.env=production` (set via `APP_ENV`).

To run them anyway — for example during a staging reset or a one-off recovery — set
`ARVEL_ALLOW_DESTRUCTIVE=1` in the shell for that single invocation:

```bash
ARVEL_ALLOW_DESTRUCTIVE=1 arvel migrate:fresh
```

`ARVEL_ALLOW_DESTRUCTIVE` is intentionally **not** a `config/app.py` key. Putting it
there would permanently disable the guard. It must be set explicitly every time so
the protection can't be silently left off.

### Database & introspection

```bash
arvel db:seed                    # run database/seeders/database_seeder.py
arvel db:seed --seeder UserSeeder
arvel db:show                    # connection metadata + table summary
arvel db:table <name>            # columns, indexes, foreign keys
arvel model:show <app.Model>     # resolve a model FQN and print its schema
arvel model:prune                # delete stale rows on every Prunable model
arvel channel:list               # registered broadcast channels
arvel event:list                 # event → listener wiring
```

`model:prune` calls `prunable_query().delete()` on every concrete model that mixes in `Prunable`. Define `prunable_query()` on your model to control which rows get removed. See [Arvent — Prunable](arvent.md#prunable).

### Cache

```bash
arvel cache:clear                # flush the default store
arvel cache:clear --store=redis  # flush a named store
arvel cache:forget <key>         # remove one key
```

The cache table migration is published with
`arvel vendor:publish --tag=arvel-cache` (see the *Generators* section above).

### Queue (requires the queue subsystem to be registered)

```bash
arvel queue:work                 # start a worker on the default queue
arvel queue:work --queue=high    # consume a specific queue
arvel queue:work --stop-when-empty
arvel queue:size                 # pending job count on the default queue
arvel queue:size --queue=high    # pending job count on a named queue
arvel queue:failed               # list dead-letter jobs
arvel queue:retry <uuid>         # re-dispatch one failed job
arvel queue:flush                # delete all failed jobs
arvel queue:forget <uuid>        # delete one failed job
arvel queue:restart              # signal every worker to exit gracefully
arvel queue:clear <queue>        # purge a single queue
arvel queue:prune-failed --hours 48   # delete failed jobs older than N hours
```

`queue:restart` writes a UTC timestamp into the cache key
`arvel:queue:restart`. `Worker.run_until` polls the key once per loop
and shuts down cleanly when it sees a marker newer than its own start
time. Workers are expected to be supervised (systemd, supervisord,
Kubernetes) and restart on their own.

### Scheduler

```bash
arvel schedule:work              # run the scheduler loop (long-lived)
arvel schedule:work --once       # fire any due tasks once and exit
arvel schedule:run               # alias for `schedule:work --once`
arvel schedule:list              # list every registered scheduled task
arvel schedule:interrupt         # tell the running loop to exit at next tick
arvel schedule:pause             # suspend task dispatch without stopping the loop
arvel schedule:continue          # resume after schedule:pause
```

`schedule:interrupt`, `schedule:pause`, and `schedule:continue` communicate with the running `schedule:work` process via a cache marker (the same pattern as `queue:restart`). The loop polls for the marker at each tick boundary. A cache store must be configured for the signals to take effect. See [Task Scheduling — Controlling the scheduler](scheduling.md#controlling-the-scheduler).

### Production caches

Pre-compile slow-to-build resources before serving traffic.

```bash
arvel config:cache               # serialize config/*.py to bootstrap/cache/config.json
arvel config:clear               # delete the config cache (next boot reads config/*.py)
arvel view:cache                 # compile all Jinja templates to bootstrap/views/
arvel view:clear                 # delete the bytecode cache and reset the Jinja environment
arvel optimize                   # run config:cache + view:cache in one step
arvel optimize:clear             # run config:clear + view:clear in one step
```

`config:cache` serializes all primitive-valued config attributes from the loaded `config/*.py` modules to `bootstrap/cache/config.json`. On the next boot, `ApplicationBuilder` reads the cache instead of loading Python files — skipping module import overhead. Run `config:clear` to force a fresh read after a config change.

`view:cache` pre-compiles all Jinja templates to Jinja's bytecode format in `bootstrap/views/`. Subsequent renders skip the parse step. Run `view:clear` to rebuild after template changes.

`optimize` runs both steps in sequence. Use it at the end of your deploy script. `optimize:clear` is the inverse — run it before a local hot-reload cycle.

> **Note**: `route:cache` and `event:cache` are not yet available. FastAPI routes include Python callables that can't be serialized to disk.

### Maintenance mode

```bash
arvel down                       # enter maintenance mode
arvel down --secret <token>      # use a specific bypass token (instead of a random one)
arvel down --retry 60            # set the Retry-After header to 60s
arvel down --refresh 15          # set the Refresh header (browser auto-reload)
arvel up                         # exit maintenance mode
```

`arvel down` writes a JSON marker to `storage/framework/down`. When the
marker is present, `MaintenanceModeMiddleware` (auto-wired by
`HttpServiceProvider` when `MaintenanceModeManager` is bound in the
container) responds with `503 Service Unavailable` plus the optional
`Retry-After` and `Refresh` headers.

Operators can bypass the page by either visiting
`https://your-app/?bypass=<secret>` once (the response sets a
`HttpOnly`, `SameSite=Lax`, `Secure`-on-HTTPS cookie) or by sending
the cookie directly. The bypass token is generated with
`secrets.token_urlsafe(32)` (256 bits) and compared in constant time.

### Broadcasting (requires `arvel[broadcasting]`)

```bash
arvel reverb:start                       # start the Reverb WebSocket server
arvel reverb:start --host=0.0.0.0 --port=8080
```

### Auth

```bash
arvel auth:clear-resets          # delete expired rows from password_reset_tokens
```

### Ops / infra

```bash
arvel serve                      # run public.asgi:asgi under uvicorn (dev)
arvel serve --host 0.0.0.0 --port 8000 --reload
arvel route:list                 # list every registered route (Method, URI, Name, Action, Middleware)
arvel route:list --filter api    # case-insensitive substring filter on the path
arvel route:list --json          # raw JSON for piping into jq
arvel storage:link               # symlink public/storage → storage/app/public
arvel storage:unlink             # remove the public/storage symlink (idempotent)
arvel key:generate               # write a new APP_KEY into .env
arvel key:generate --show        # print the key, don't write .env
arvel shell                      # interactive REPL with app + facades in scope
arvel tinker                     # alias for `shell`
arvel about                      # framework + runtime version info
arvel test [pytest args...]      # forward to pytest.main() in-process
```

### Project scaffolding

Use the same `arvel` binary you'd run inside a project — `new` is the one
command that's allowed *outside* an Arvel project:

```bash
arvel new my-app                 # create a new Arvel project
arvel new --help                 # list scaffolding flags
arvel new my-app --no-install    # skip `uv sync`
arvel new my-app --python 3.14   # pin requires-python in pyproject.toml
```

## Writing your own commands

Console commands subclass `arvel.console.Command` and are registered via Python entry-points or a service provider's `commands()` method. There is no autodiscovery of `app/Console/Commands/` — registration is explicit.

### Subclassing `Command`

```python
# app/console/commands/send_invoices.py
from typing import Annotated, ClassVar

import typer

from arvel.console import Command, Context


class SendInvoicesCommand(Command):
    name: ClassVar[str] = "invoices:send"
    help: ClassVar[str] = "Dispatch invoice send jobs for a given month."
    needs_application: ClassVar[bool] = True  # opt into framework DI

    def register(self, app: typer.Typer) -> None:
        cmd_self = self

        def _callback(
            month: Annotated[str, typer.Option(help="YYYY-MM")],
        ) -> None:
            code = cmd_self.send(month)
            if code != 0:
                raise typer.Exit(code)

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        # Not used here because register() drives Typer directly.
        # Override handle() instead of register() for no-arg commands.
        raise NotImplementedError

    def send(self, month: str) -> int:
        # `self.app` is the framework Application (because needs_application = True).
        # Use it to resolve services from the container.
        ...
        return 0
```

For a simple no-arg command, override `handle(ctx)` and skip `register()`:

```python
class HelloCommand(Command):
    name: ClassVar[str] = "hello"
    help: ClassVar[str] = "Say hi."

    def handle(self, ctx: Context) -> int:
        ctx.info("Hello, world!")
        return 0
```

### Registering the command

Commands are picked up from two sources, in this order (later wins on name collision):

**(a) Python entry-points** — for commands that don't need the framework container:

```toml
# pyproject.toml
[project.entry-points."arvel.commands"]
"hello" = "app.console.commands.hello:HelloCommand"
```

**(b) A service provider's `commands()` method** — for commands that need DI:

```python
# app/providers/invoice_service_provider.py
from arvel.providers.service_provider import ServiceProvider

from app.console.commands.send_invoices import SendInvoicesCommand


class InvoiceServiceProvider(ServiceProvider):
    def commands(self) -> list[type[SendInvoicesCommand]]:
        return [SendInvoicesCommand]
```

Register the provider in `bootstrap/app.py` so `ConsoleServiceProvider.boot()` picks the command up. Provider commands are wired after framework boot, so they can resolve services from the container in their `register()` body.

### The `Context` I/O surface

`Context` mirrors Laravel's command I/O so the migration story is obvious:

| Method | Stream | Use for |
|---|---|---|
| `ctx.info(msg)` | stdout | Status messages |
| `ctx.line(msg)` | stdout | Plain output |
| `ctx.warn(msg)` | stdout | Non-fatal warnings |
| `ctx.comment(msg)` | stdout | Annotations |
| `ctx.alert(msg)` | stdout | High-visibility output |
| `ctx.error(msg)` | stderr | Failure messages (pair with non-zero exit) |
| `ctx.newline(n=1)` | stdout | Blank lines |

### Exit codes

Return an `int` from `handle()` or raise `typer.Exit(code)` from the Typer callback. The convention across built-ins:

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | The command body raised (user code / migration / seeder failed) |
| `2` | Bootstrap failure (missing project, missing container binding, bad input) |

## Scheduling commands

See [Task Scheduling](scheduling.md) for running console commands on a cron-like schedule.

## See also

- [Task Scheduling](scheduling.md) — cron-style command scheduling.
- [Queues](queues.md) — long-running commands as queued jobs.
- [Console Tests](console-tests.md) — testing console commands.
