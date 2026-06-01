# ADR-123 — CLI optionally bootstraps a framework Application via `bootstrap/app.py`

**Status**: Accepted
**Date**: 2026-05-19
**Supersedes**: none
**Superseded by**: none
**Related**: WI-020 (`ConsoleServiceProvider`), FB-021-001, FB-021-002

## Context

After WI-020, `ConsoleServiceProvider` exists and `arvel.console.Application.run()` can dispatch a command in-process. But neither was reachable from the `arvel` CLI script. `arvel.console.entrypoint.main()` only knew about entry-point-discovered commands — it never instantiated the framework `arvel.application.Application`. So three categories of commands were stuck:

1. **Queue commands** (`queue:work`, `queue:failed`, `queue:retry`, `queue:flush`, `queue:forget`) need a `QueueManager` from DI. Today they aren't registered at all.
2. **Scheduler commands** (`schedule:work`, `schedule:list`) need the user's `Schedule` (typically wired in `app/console/kernel.py::Kernel.schedule()`). Today they build a fresh empty `Schedule()` and the user's tasks are invisible.
3. **Shell command** needs `app`, `container`, and the facade set in the REPL namespace. Today it returns `{"sys": sys}`.

The unifying root cause: the `arvel` CLI never bootstraps a framework `Application`, so its commands have no container to pull from. Three approaches were considered.

### Options

**Option 1 — Always bootstrap.** Every `arvel <anything>` invocation calls `bootstrap_framework_application()`. Pro: simple, uniform. Con: startup latency for `arvel --help`, `arvel about`, and every `arvel make:*` invocation — all of which work fine without a container. Hits NFR-021-03 (≤1.0s warm `arvel --help`) immediately because the user's `bootstrap/app.py` may import every provider and run every `register()`.

**Option 2 — Bootstrap on demand via a wrapper script.** Add a separate `arvel-app` binary that bootstraps; keep `arvel` as the plain Typer dispatcher. Pro: clear separation. Con: doubles the user-facing CLI surface (Laravel devs expect one `arvel`/`artisan`); confusing migration story; every doc page would have to explain when to use which binary.

**Option 3 — Lazy opt-in via class marker.** Commands that need a container declare `needs_application: ClassVar[bool] = True`. The entrypoint checks the matched command before bootstrap, only bootstraps when at least one registered (and-about-to-be-invoked) command opts in. Pro: zero overhead for the common help/about/make:* paths; explicit opt-in is type-checkable; integrates cleanly with WI-020's `ConsoleServiceProvider`. Con: two-kinds-of-command in the class hierarchy.

## Decision

**Option 3.** A new module `arvel.console.bootstrap` exposes:

```python
def find_project_root(start: Path | None = None) -> Path | None: ...
def bootstrap_framework_application(base_path: Path | None = None) -> Application | None: ...
```

`Command` grows `needs_application: ClassVar[bool] = False` (default off, opt-in to on).

`entrypoint.main()`:
1. Resolves the requested command name from `sys.argv`.
2. If outside a project (no `bootstrap/app.py` in cwd-or-up-to-4-ancestors) AND the command isn't in the always-allowed set (`--help`, `--version`, `about`, `make:*`, `key:generate`): print the migration message and exit 2.
3. Otherwise: call `_bootstrap_if_needed(commands)` — which checks if ANY discovered command has `needs_application=True` AND we have a project root. If so: call `bootstrap_framework_application()`, `app.boot()`, and merge container-resolved commands into the discovered list (container wins on name collision).
4. Run the Typer app.

## Consequences

**Positive:**

- Queue commands work end-to-end at the CLI level — the existing `QueueServiceProvider.commands()` method finally has somewhere to deliver them.
- `schedule:list` / `schedule:work` honour the user's `Kernel.schedule()`.
- `shell` REPL has `app`, `container`, `Cache`, `Auth`, etc. in scope.
- `arvel --help` / `arvel about` / `arvel make:*` stay fast (no bootstrap).
- Project-defined commands can shadow built-ins via the container-wins precedence rule.

**Negative:**

- One new module (`arvel.console.bootstrap`, ~100 LoC).
- Two-kinds-of-command in the hierarchy. Mitigated by `needs_application` being a single boolean ClassVar (low cognitive load) and an explicit comment on `Command` explaining the marker.
- The `app: "Application | None"` attribute on `Command` is `Optional` because not every command opts in. Commands that DO opt in must still handle the case where bootstrap failed (e.g., import error in the user's `bootstrap/app.py` propagates rather than being swallowed — but `needs_application=True` commands MAY still be listed via `--help` without a project). Documented by example in DXD-021 §2.5.

**Neutral:**

- `bootstrap/app.py::create_application()` is now load-bearing. The `arvel-new` scaffolder must emit this file (it already does as of WI-004).

## Implementation notes

- Discovery walks up `_MAX_ANCESTOR_DEPTH = 4` parents of cwd. Configurable later via env var if monorepo needs grow beyond this.
- `bootstrap_framework_application()` propagates `ImportError` from the user's `bootstrap/app.py` — the user wants to see that traceback, not have it swallowed.
- The merge logic uses a dict by `Command.name` for O(1) collision detection; container commands replace entry-point ones in the order: entry-points first, container second (last-write-wins → container wins).
- Tests cover: no `bootstrap/app.py` (returns None), valid `bootstrap/app.py` (returns Application), broken `bootstrap/app.py` (propagates ImportError), nested cwd (walks ancestors up to 4 levels), missing `create_application` (logs warning + returns None).
