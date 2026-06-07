# Needs-based CLI bootstrap — design

**Date:** 2026-06-05
**Author:** Squad OS / Product Engineer
**Status:** Approved (autonomous design pass)
**Related code:** `packages/arvel/src/arvel/console/`, `packages/arvel/src/arvel/application/application.py`, `packages/arvel/src/arvel/providers/*`

## Problem

`arvel`'s CLI runs every command inside a project through the **same** boot path:

```
asyncio.run(async_main(...))
  → bootstrap_framework_application()              # loads bootstrap/app.py
  → create_application()                            # register() on ALL providers
  → await framework_app.boot()                      # boot() on ALL providers
  → <dispatch>
  → await framework_app.shutdown()
```

That means `arvel make:controller Post` — a pure file generator — still:

- Pings the database (`DatabaseServiceProvider.boot()` does `SELECT 1`),
- Builds the FastAPI/Starlette router,
- Boots the OTel SDK,
- Connects to Redis (cache, queue),
- Opens SMTP for mail,
- Walks `app/console/kernel.py` for scheduled tasks,
- Connects whatever the user's providers connect to.

The only declarative knob today is `Command.needs_application: bool`, which gates **binding** `self.app` — not what runs. Boot is all-or-nothing.

A secondary problem on `openapi:export`: `--output` rejects any path outside the project root, so the e-commerce kit's Makefile is stuck on `--stdout > ../frontend/openapi.yaml` shell redirection. Mixing the spec content on stdout with the banner and the "OpenAPI spec written to ..." status makes the banner awkward — users either suppress it or accept that running `make api-generate` produces ANSI noise in the captured stream.

## Chosen approach — declarative `requires` + provider subsystem tags

Each `Command` declares the subsystems it depends on. Each `ServiceProvider` declares which subsystem it serves. The CLI bootstrap intersects the two and runs `register()` + `boot()` on only the matching providers. Everything else stays cold.

### 1. Subsystem enum (single source of truth)

```python
# arvel/console/_subsystem.py
from enum import StrEnum

class CliSubsystem(StrEnum):
    # Foundation — always loaded inside a project. Cheap; no I/O.
    CONFIG = "config"
    LOG = "log"
    LANG = "lang"
    CONTEXT = "context"

    # Opt-in subsystems.
    OBSERVABILITY = "observability"
    DATABASE = "database"
    HTTP = "http"            # Router, exception handler, rate-limit store
    SCHEDULER = "scheduler"
    QUEUE = "queue"          # depends on DATABASE
    CACHE = "cache"
    MAIL = "mail"
    STORAGE = "storage"
    BROADCAST = "broadcast"
    AUTH = "auth"            # depends on DATABASE
    EVENTS = "events"

    # Catch-all: include user-defined providers (and their commands()).
    USER_PROVIDERS = "user_providers"
```

Dependencies are declared in `_subsystem.py` as a directed graph (e.g., `QUEUE → DATABASE`, `AUTH → DATABASE`). The bootstrap takes a `Command.requires` set, computes the **transitive closure** under those edges, and uses the result as the boot set.

### 2. `Command.requires`

```python
class Command:
    name: ClassVar[str]
    help: ClassVar[str] = ""
    requires: ClassVar[frozenset[CliSubsystem]] = frozenset()
    owns_process: ClassVar[bool] = False
    app: FrameworkApplication | None = None
```

- Default `requires = frozenset()` → only foundation providers (Config, Log, Lang, Context) load. Plus, of course, the command itself.
- Generators (`make:*`, `new`, `key:generate`, `about`) keep an empty `requires`. They still work outside a project, exactly as today.
- `needs_application: bool` is **removed**. Its only legacy meaning ("bind `self.app`") becomes: a command has `self.app` bound iff a framework `Application` was bootstrapped, which now happens iff `requires` is non-empty *or* `requires_project_context = True` (a separate, cheap flag for commands like `serve` that need `base_path` but no boot).

### 3. `ServiceProvider.subsystem`

```python
class ServiceProvider:
    subsystem: ClassVar[CliSubsystem | None] = None  # None = foundation
```

| Provider | `subsystem` |
|---|---|
| `ConfigServiceProvider` | `CONFIG` |
| `LogServiceProvider` | `LOG` |
| `LangServiceProvider` | `LANG` |
| `ContextServiceProvider` | `CONTEXT` |
| `ObservabilityServiceProvider` | `OBSERVABILITY` |
| `DatabaseServiceProvider` | `DATABASE` |
| `HttpServiceProvider` | `HTTP` |
| `SchedulerServiceProvider` | `SCHEDULER` |
| `CacheServiceProvider` | `CACHE` |
| `QueueServiceProvider` | `QUEUE` |
| `MailServiceProvider` | `MAIL` |
| `StorageServiceProvider` | `STORAGE` |
| `BroadcastServiceProvider` | `BROADCAST` |
| `AuthServiceProvider` | `AUTH` |
| `EventServiceProvider` | `EVENTS` |
| `ConsoleServiceProvider` | foundation (`None`) — always last |
| any user provider (e.g., `AppServiceProvider`) | `USER_PROVIDERS` (default for providers loaded from `bootstrap/providers.py`) |

Foundation providers (`subsystem = None`) always load. User providers (from `bootstrap/providers.py`) default to `USER_PROVIDERS` — a command opts in by including `CliSubsystem.USER_PROVIDERS` in `requires`. Plug-in framework providers (e.g., `ImageServiceProvider` shipped by `arvel-image`) can set their own subsystem; if they don't, they bucket under `USER_PROVIDERS`.

### 4. Bootstrap algorithm

```
plan_bootstrap(command_name, argv) -> BootPlan:
    1. If command is None / unknown / --help / --version:
         return BootPlan.empty()                       # no framework, no project

    2. Load the resolved command (entry-point only — providers haven't run yet).

    3. If command.requires is empty and not command.requires_project_context:
         return BootPlan.empty()                       # pure entry-point path

    4. project_root = find_project_root()
       if project_root is None and command.requires_project_context:
         exit with the existing "no project" error.

    5. required_subsystems =
         {CONFIG, LOG, LANG, CONTEXT}                  # foundation, always on
         | closure(command.requires)                   # transitive deps

    6. Build the provider chain:
         - load bootstrap/app.py and ApplicationBuilder as today,
         - resolve_provider_chain() now returns ALL providers,
         - filter by: subsystem is None  OR  subsystem in required_subsystems
                  OR  (subsystem == USER_PROVIDERS and USER_PROVIDERS in required_subsystems)
         - ConsoleServiceProvider stays pinned last.

    7. Run register() and boot() on the filtered chain only.

    8. shutdown() in reverse, on the same filtered chain.
```

Single command, one knob (`requires`), no branchy code in the entrypoint per subsystem.

### 5. Command requirement matrix (built-ins)

> See `docs/console/cli-architecture.md` for the catalog. The values below seed `requires` per command.

| Group / Command | `requires` |
|---|---|
| `make:*`, `new`, `about`, `key:generate`, `--help`, `--version` | `∅` |
| `config:show`, `config:cache`, `config:clear`, `optimize`, `optimize:clear`, `view:cache`, `view:clear` | `∅` (Config is foundation) |
| `key:rotate`, `auth:clear-resets` | `DATABASE`, `AUTH` |
| `migrate`, `migrate:rollback`, `migrate:status`, `migrate:reset`, `migrate:fresh`, `migrate:refresh` | `DATABASE` |
| `db:seed`, `db:show`, `db:table`, `model:show`, `model:prune` | `DATABASE`, `USER_PROVIDERS` (seeders/models live in user code) |
| `cache:clear`, `cache:forget` | `CACHE` |
| `queue:work`, `queue:failed`, `queue:retry`, `queue:flush`, `queue:forget`, `queue:size`, `queue:restart`, `queue:clear`, `queue:prune-failed` | `QUEUE` (→ `DATABASE`), `USER_PROVIDERS` |
| `schedule:work`, `schedule:list`, `schedule:run`, `schedule:interrupt`, `schedule:pause`, `schedule:continue` | `SCHEDULER`, `USER_PROVIDERS` (Kernel lives in user code) |
| `route:list`, `event:list`, `channel:list` | `HTTP` (or `EVENTS`/`BROADCAST` resp.), `USER_PROVIDERS` |
| `openapi:export`, `openapi:validate` | `HTTP`, `USER_PROVIDERS` |
| `serve` | none booted; `requires_project_context = True`; `owns_process = True` (uvicorn re-imports the ASGI app and boots it via lifespan) |
| `shell`, `tinker` | all subsystems + `USER_PROVIDERS` |
| `down`, `up` | `HTTP` (MaintenanceModeManager) |
| `storage:link`, `storage:unlink` | `STORAGE` |
| `vendor:publish`, `config:publish` | `USER_PROVIDERS` (publishables come from providers' `register()`) |
| `test` | `∅` (delegates to pytest) |
| `reverb:start` | `BROADCAST`; `owns_process = True` |

### 6. `openapi:export` output

- `--output` accepts any path: absolute, relative-to-CWD, or escaping the project root. No `_safe_output_path` check.
- Status text (`OpenAPI spec written to ...`) writes to **stderr** (it's framework chatter, not data).
- Spec content writes to file by default; `--stdout` keeps the option to emit on stdout for piping.
- New: `--output -` is sugar for `--stdout` (POSIX convention).
- Banner stays on stderr. With the above, a CI invocation looks like:

  ```
  arvel openapi:export --output ../frontend/openapi.yaml --format yaml
  ```

  Spec → file. Banner → stderr (visible in TTY, suppressed in CI as before). Nothing on stdout. The kit Makefile drops the shell redirect entirely.

### 7. Why not...

- **Lazy provider boot (Option C: boot a provider on first `container.make()`)** — provider `boot()` is async; turning every `make()` into an async-aware call is invasive, and we lose the ability to filter the *register* pass too.
- **Per-command boot functions** — push boot logic into the command files; loses the central provider lifecycle and bypasses `ServiceProvider.boot()` discipline.
- **`needs_application` overload** — too coarse. We need finer granularity than "yes/no framework".

### 8. Cold-start expectations

| Command (inside e-commerce kit) | Before (full boot) | After (needs-based) | Notes |
|---|---|---|---|
| `arvel make:controller Foo` | ~3.9s | <0.5s | no project boot, no provider load |
| `arvel migrate` | ~3.9s | <1.5s | Config + Log + Lang + Context + Database |
| `arvel openapi:export -o ...` | ~3.9s | ~2.5s | HTTP + user providers (routes mounted in register) |
| `arvel queue:work` | ~3.9s | ~3.0s | Database + Queue + user providers |
| `arvel shell` | ~3.9s | ~3.9s | full boot — by design |

These are rough targets; the benchmark in `benchmarks/` gets a new harness as part of the WI.

## Out of scope

- Adding new commands.
- Reworking `Command.call()` for arg passthrough (separate WI).
- Moving `cache:*` and `schedule:run` off nested `asyncio.run()` (separate WI).

## Open questions

None — answers assumed in autonomous mode are noted inline in user-story `Notes`.

## Next phase

`/write-user-stories` → epic `001-needs-based-cli-bootstrap.md` in `docs/backlog/`.
