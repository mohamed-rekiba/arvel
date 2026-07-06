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

`arvel new` names the package/app from the target path's **basename**, not the whole path, so an
absolute (or relative, or trailing-slash) path all work the same way:
`arvel new /abs/path/my-app` scaffolds at `/abs/path/my-app` with the package named `my-app`
(pyproject `name`, the welcome page title, `--package`'s `arvel-my-app`) — not the full path.

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
| `make:event <Name>` | scaffold a domain event (`app/events/`) |
| `make:listener <Name>` | scaffold an event listener (`app/listeners/`; register via `Event.listen`) |
| `make:cast <Name>` | scaffold a custom attribute cast (`app/casts/`; use in a model's `__casts__`) |
| `make:observer <Name>` | scaffold a model observer (`app/observers/`; register via `Model.observe()`) |
| `make:enum <Name>` | scaffold a string-backed enum (`app/enums/`) |
| `make:exception <Name>` | scaffold an exception class (`app/exceptions/`) |
| `make:test <Name>` | scaffold a pytest test (`tests/test_<name>.py`) |
| `route:list` | tabulate the app's routes (methods, path, name) |
| `migrate` / `migrate:rollback` | apply / revert migrations |
| `migrate:fresh` | drop all tables, then re-run every migration |
| `migrate:refresh` | roll back all migrations, then re-run them |
| `db:wipe` | drop all tables without re-migrating |
| `db:seed` | run the app's database seeder |
| `cache:clear` | flush the default cache store |
| `key:generate` | generate an app key and write it to `.env` as `APP_KEY` |
| `storage:link` | symlink `public/storage` → `storage/app/public` |
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
- **every model by its short name** (autoloaded from `app/models/`, -Tinker style).

```python
arvel tinker
>>> await User.find(1)          # top-level await — no asyncio.run needed
>>> Post.where(...)     # models reachable by name, no import
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

### Frequency helpers, gates, and timezones

Beyond `cron`/`hourly`/`daily`/`daily_at`, the same fluent cadence covers the common cases:

```python
Schedule.call(archive_old_logs).weekly()                    # Sunday, midnight
Schedule.call(close_books).monthly()                         # the 1st, midnight
Schedule.call(reconcile).quarterly()                         # Jan/Apr/Jul/Oct 1st
Schedule.call(renew_licenses).yearly()                        # Jan 1st, midnight
Schedule.call(sync_inventory).twice_daily(1, 13)              # 01:00 and 13:00
Schedule.call(send_report).daily().weekdays()                 # Mon–Fri only
Schedule.call(backup).daily().weekends()                      # Sat/Sun only
Schedule.call(poll_api).hourly().between("09:00", "17:00")    # only during business hours
Schedule.call(flush_cache).hourly().when(lambda: is_low_traffic())
Schedule.call(cleanup).daily().skip(lambda: is_maintenance_window())
Schedule.call(nightly_job).daily_at("02:00").environments("production")
Schedule.call(send_invoices).daily_at("09:00").timezone("America/New_York")
```

`when`/`skip` take a plain (sync) predicate; `environments(*envs)` gates by `config('app.env')`;
`timezone(tz)` matches the cron expression against the current moment shifted into `tz` instead
of as given.

### Hooks

`before`/`after` always run around the task; `on_success`/`on_failure` run based on the outcome
(`after` still runs even if the task raised):

```python
(
    Schedule.command("reports:generate")
    .daily()
    .before(lambda: log.info("starting report"))
    .on_success(lambda: notify_slack("report ready"))
    .on_failure(lambda: notify_slack("report failed"))
    .after(lambda: log.info("report task done"))
)
```

### `on_one_server` and `without_overlapping` (real locks, not a no-op)

Running `schedule:run` on more than one node? `on_one_server()` makes sure a task fires only
**once** across all of them — arbitrated by a real `CacheLock` (story 06), not a per-process flag:

```python
Schedule.command("reports:generate").daily().on_one_server()
```

`without_overlapping(expires=3600)` is the single-node version: it skips a tick while the
**previous** run of the same task is still in flight (e.g. a slow report that occasionally runs
past its next scheduled minute), instead of starting a second, overlapping one:

```python
Schedule.command("reports:generate").every_minute().without_overlapping(expires=1800)
```

Both lock on the event's identity — its callback's qualified name by default, or an explicit
`.name("...")` when the callback has none (a lambda/closure) or two events would otherwise
collide. They need a cache bound — the `QueueServiceProvider` wires the app's cache into
`Schedule` automatically when one is configured, so this normally needs no extra setup; without a
cache configured at all, an event using either one fails loudly (logged by `run_due`, same as any
other failing task) rather than silently skipping the coordination it promised.

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

### Progress + output on a long seed

A big seed (thousands of rows, image downloads) shouldn't run silently. `db:seed` injects a live
console into your seeder, so a `Seeder` has the same output surface as a command — wrap a slow loop in
`self.with_progress_bar(...)` and print section headers with `self.line(...)`:

```python
class DatabaseSeeder(Seeder):
    async def run(self):
        self.line("→ products")
        for row in self.with_progress_bar(catalog, label="products"):
            product = await Product.create(**row)
            await download_images(product)      # the loop body may await; the bar advances per item
```

The bar renders on a terminal and is quiet when output is piped/redirected (no control codes in logs).
Run outside `db:seed` — in a test or a script — and the output defaults to a silent no-op, so
`with_progress_bar` just iterates. Child seeders started with `call`/`call_once` inherit the same
console. (`self.info` and the full `self.output` handle are available too.)

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

### The `Command` base class (I/O, prompts, `argument()`/`option()`)

`make:command` scaffolds a class command subclassing `arvel.console.Command` — it gets typed
stdout/stderr I/O, interactive prompts, and accessors for its own parsed CLI tokens:

```python
from typing import Any
from arvel.console import Command

class SendReports(Command):
    signature = "report:send {user} {--force}"
    description = "Send the weekly report to a user"

    async def handle(self, *deps: Any) -> None:
        user = self.argument("user")
        force = self.option("force")
        if not force and not self.confirm(f"Send the report to {user}?"):
            self.warn("cancelled")
            return
        self.info(f"sending to {user}...")
        for _ in self.with_progress_bar(range(10)):
            ...  # do the work
        self.table(["user", "sent"], [[user, "yes"]])
```

**Output** (`info`/`line`/`comment`/`question` → stdout; `error`/`warn` → stderr; `new_line(n)`;
`table(headers, rows)`; `with_progress_bar(iterable)`) is built on click's own `echo`/`style`/
`progressbar` (typer's backing library — the console layer may not import `rich` directly; see
"How it works" below) — no new dependency, and every method is stream-testable: `Command(output=
ConsoleOutput(out=buf, err=buf))` (or construct a bare `ConsoleOutput(out, err)` directly) routes
output to injected streams instead of the real terminal.

**Prompts**: `ask(label, default=None)`,
`secret(label)` (no echo), `confirm(label, default=False)`, `choice(label, options, default=None)`
(re-prompts on an invalid pick), `anticipate(label, suggestions, default=None)` (free text, with
suggestions shown as a hint). Available as free functions or as `Command` methods
(`self.ask(...)`, …); both take an injectable `Prompter` so tests seed answers instead of reading
real stdin:

```python
from arvel.console.prompts import Prompter, confirm

confirm("Proceed?", prompter=Prompter(["y"]))          # -> True, no terminal touched
Command(prompter=Prompter(["Ada", "y"]))                # a whole command's prompts, pre-seeded
```

**`argument()`/`option()`** read the values the kernel parsed for *this* invocation — the kernel
stashes them on the instance (via `bind_parsed`) right before `handle()` runs, split by the
command's own `signature` grammar (see below).

### Signature grammar

Both class commands (`Command.signature`) and closures (`Console.command(signature, handler)`, see
below) share one grammar, parsed by `arvel.console.closure.parse_signature`:

| Token | Meaning |
|-------|---------|
| `{name}` | required positional argument |
| `{name?}` | optional positional argument |
| `{name=default}` | positional argument with a default |
| `{name*}` | variadic positional (collects into a list) |
| `{--flag}` | boolean option (`--flag` present → `True`) |
| `{--opt=}` | value option (`--opt value`) |
| `{--opt=*}` | multi-value option (repeatable: `--opt a --opt b` → `["a", "b"]`) |
| `{--Q\|queue}` | a shortcut (`-Q`/`--queue`) — combine with `=`/`=*` for a value/multi shortcut |

An optional/defaulted/variadic positional must come last (a required one after it is a signature
error, raised at registration).

### Invoking a command programmatically (`Cli.call`)

`arvel.console.kernel.Cli.call(name, args=None) -> int` runs a command in-process and returns
its exit code (`call_silently` additionally swallows its stdout/stderr):

```python
from arvel.console.kernel import Cli

code = Cli.call("migrate")                              # a built-in — argv-shaped args
code = Cli.call("report:send", {"user": "ada", "--force": True})  # app-registered
Cli.call_silently("cache:clear")
```

Built-in framework commands (`migrate`, `make:*`, …) dispatch through the same click command the
CLI uses (`args` is a `dict` of CLI-shaped values or a raw `list[str]` of argv tokens). Commands
registered by *your* app (a `routes/console.py` closure, or a provider's `commands()`) dispatch
**directly against the currently active application** — call `Cli` from inside a booted app (a
request, another command, a scheduled task, or a test that set one up), not as a bare script;
there's no project to boot here.

### Closures (`routes/console.py`)

```python
from arvel import Console

async def greet(name: str, force: bool = False) -> None: ...

Console.command("greet {name} {--force}", greet)
```

Same signature grammar as class commands; the parsed tokens are passed to the handler by name (the
rest is autowired from the container).

### `stub:publish`

The `make:*` generators write from a built-in template per kind. `arvel stub:publish` copies every
one of those templates into `./stubs/<kind>.stub` (plus `migration.create.stub` /
`migration.generic.stub` / `test.stub`); once a stub is published, the matching generator reads
*that* file instead of its built-in template — edit it to change what gets scaffolded:

```bash
arvel stub:publish            # writes ./stubs/*.stub
arvel stub:publish --force    # overwrite already-published stubs
$EDITOR stubs/model.stub      # customize — make:model now uses this
```

## Maintenance mode

`arvel down` / `arvel up` flip the app into/out of maintenance (503) via
`PreventRequestsDuringMaintenance`, a global middleware. The flag lives in the app's default cache
driver, so its reach follows your cache (`array` = this process only; Redis = every instance).

```bash
arvel down --secret=letmein --allow=10.0.0.1 --retry=120 --render=maintenance
arvel up
```

- `--secret=S` — a request to `?secret=S` bypasses the 503 (and sets a cookie so later requests
  from the same visitor bypass without repeating the query param).
- `--allow=IP` — repeatable; that IP always bypasses.
- `--render=NAME` — reads `resources/views/NAME.html` **once, at `down` time** (a raw file read,
  not the Jinja view engine — maintenance mode must not depend on services that might themselves be
  why the app is down) and serves it verbatim as the 503 body instead of the default JSON message.
- `--retry=N` — the `Retry-After` header hint (seconds).

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
