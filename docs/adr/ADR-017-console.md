# ADR-017 — Console / CLI

**Status**: Accepted
**Date**: original decisions 2026-05-17 – 2026-05-20; merged into one ADR on 2026-06-07 during the WI-arvel-005 consolidation pass
**Scope**: CLI packaging, Typer single-command promotion, framework bootstrap, command I/O surface MVP, make-stub templates, single-arvel-binary consolidation.

## Why this is one ADR

Six joints of the same `arvel` binary — packaging, CLI library, bootstrap, I/O, code generation, single-entrypoint consolidation. One ADR makes the design legible.

---

## § 1 — `arvel-cli` packaging strategy

**Originally**: ADR-121 · Date: 2026-05-17

### Context

Per constitution Article III §3, `arvel-cli` is a separate PyPI
package from `arvel`. WI-004 turns it from a stub-that-exits-2 into a real
implementation that scaffolds the canonical layout (ADR-001 § 5) into a target
directory.

Three sub-decisions need to be locked in for the implementation:

1. **Where does the skeleton live?**
2. **What CLI framework drives `arvel new`?**
3. **How are tokens like `{{ project_name }}` substituted?**

#### Skeleton storage options

| Option | Pros | Cons |
|---|---|---|
| A. **Inside the wheel as packaged data** (`arvel_cli/skeleton/`) read via `importlib.resources` | One artifact to install; works offline; deterministic version match between installer and skeleton | Wheel size grows with skeleton; binary-ish content inside wheel |
| B. Separate `arvel-skeleton` package fetched at runtime | Smaller installer | Two packages to coordinate; extra network call; breaks offline use |
| C. Git clone from a known repo at install time | Always latest | Requires git; requires network; breaks corporate firewalls; version skew |

#### CLI framework options

| Option | Pros | Cons |
|---|---|---|
| A. `argparse` (stdlib) | Zero deps | Verbose; awkward subcommands; no built-in completion |
| B. **Typer 0.19+** | Same stack as WI-005 console binary; type-driven; auto-completion | One dep (already in framework's transitive set) |
| C. `click` | Mature | One dep, and Typer wraps Click anyway |

#### Token substitution options

| Option | Pros | Cons |
|---|---|---|
| A. **`str.replace` over a small token dict** | Zero deps; trivially reviewable; impossible to introduce template injection | No conditionals, no loops, no filters — but we don't need any |
| B. Jinja2 | Powerful | Heavy dep for the three substitutions we actually make; opens template-injection surface |
| C. `string.Template` | Stdlib | `$` syntax conflicts with shell scripts in the skeleton (`.env.example` has `${DB_HOST}` placeholders) |

### Decision

1. **Skeleton storage**: Option A — packaged data inside the wheel under
   `arvel_cli/skeleton/`, read via `importlib.resources` (`Traversable`
   API).
2. **CLI framework**: Option B — Typer 0.19+.
3. **Token substitution**: Option A — literal `str.replace` with a fixed
   token dict.

#### Skeleton storage details

The skeleton tree mirrors the on-disk layout exactly, but file extensions
get a `.tmpl` suffix where templating applies:

```
arvel_cli/skeleton/
├── bootstrap/
│   ├── __init__.py
│   ├── app.py
│   └── providers.py
├── public/
│   ├── __init__.py
│   └── asgi.py
├── routes/
│   ├── __init__.py
│   ├── api.py
│   ├── console.py
│   └── web.py
├── config/
│   ├── __init__.py
│   ├── app.py.tmpl         # has {{ project_name }} token
│   └── database.py
├── app/
│   ├── __init__.py
│   ├── Http/
│   │   ├── __init__.py
│   │   ├── Controllers/__init__.py
│   │   └── Middleware/__init__.py
│   ├── Models/__init__.py
│   ├── Providers/__init__.py
│   └── Services/__init__.py
├── database/
│   ├── __init__.py
│   ├── migrations/.gitkeep
│   └── seeders/__init__.py
├── storage/.gitkeep
├── tests/
│   ├── __init__.py
│   ├── Feature/__init__.py
│   └── Unit/__init__.py
├── _dot_env_example         # → .env.example at copy time
├── _dot_gitignore           # → .gitignore at copy time
├── README.md.tmpl           # has {{ project_name }}, {{ project_name_pascal }}
└── pyproject.toml.tmpl      # has all three tokens
```

Two renaming rules at copy time:
- `*.tmpl` → strip `.tmpl` and apply token substitution.
- `_dot_*` → rename to `.<rest>` (Python packaging tooling refuses to
  include filenames starting with `.` in wheel data).

#### Typer 0.19+ pin

Installer's `pyproject.toml` declares `typer >= 0.19, < 0.20`. We pin to the
minor for now (the Typer API is stable but not 1.0). Verified `0.19.x` as
the current latest stable per `100-coding-standards.mdc` § Dependency
Version Pinning.

#### Token dict

```python
TOKENS = {
    "{{ project_name }}": <user input, validated>,
    "{{ project_name_pascal }}": <PascalCase of project_name>,
    "{{ python_version }}": <from --python flag or sys.version_info>,
}
```

The substitution function asserts that no `{{ ... }}` patterns remain in any
file post-substitution (catches typos in template files at install time,
not at user runtime).

### Consequences

**Positive**:
- `pipx run arvel-cli new my-app` works offline after first install.
- Skeleton version is exactly aligned with the installer version that
  produced it — no skew between "the installer I ran" and "the skeleton it
  used".
- Token substitution surface is tiny and reviewable (~5 lines of code).
- Typer choice means the same CLI patterns and helpers carry into WI-005's
  `arvel` console binary.

**Negative**:
- Wheel ships with the skeleton tree embedded. Current size ~5 KB total —
  negligible.
- `*.tmpl` and `_dot_*` renaming is two extra rules to remember when adding
  files. Mitigated by the post-copy assertion that no unsubstituted tokens
  remain, and by Gate #29 (no-unsubstituted-tokens) which audits the
  generated tree in CI.

**Enforcement**:
- `make smoke-skeleton` (Gate #7) generates a project end-to-end in CI.
- Adversarial path-traversal test suite (Gate #27, Stage 4b focus) covers
  malicious project names.
- New Gate #29 (Skeleton no-unsubstituted-tokens) greps the generated tree
  for `{{ ` after generation and fails the build if any token remains.

---

## § 2 — Typer Single-Command Promotion Workaround

**Originally**: ADR-122 · Date: 2026-05-17

### Context

When only one subcommand is registered with a `typer.Typer` instance, Typer
"promotes" that command to the root app — the subcommand name is dropped and the
command runs directly as the root callback. This breaks the `Application` contract
in two ways:

1. `test_application_last_registered_wins_on_collision` failed because the single
   registered command ran at root level, bypassing the name-dispatch logic.
2. Any user who builds an `Application([OneCommand()])` sees inconsistent CLI
   behaviour compared to `Application([A(), B()])`.

Typer's own documentation acknowledges this behaviour and suggests registering a
no-op root callback with `invoke_without_command=True` as the recommended
mitigation.

### Decision

`Application.__init__` registers a root callback **before** any subcommands:

```python
def _noop(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())

self.typer_app.callback(invoke_without_command=True)(_noop)
```

The callback does nothing when a subcommand is invoked, and prints help when the
CLI is called with no arguments (matching Laravel's `artisan` behaviour). The
explicit `app.callback()(fn)` call form (rather than a decorator) is used so
pyright does not flag `_noop` as an unused function.

### Consequences

- **Positive**: `Application` behaves identically regardless of how many commands
  are registered — one command, two, or twenty.
- **Positive**: `arvel` with no arguments prints a help screen, matching the
  Laravel Artisan UX.
- **Negative**: A tiny extra callback is always registered. No measurable overhead.
- **Watch out**: If Typer changes this behaviour in a future version, the `_noop`
  becomes a no-op wrapper of a no-op — harmless but can be removed.

---

## § 3 — CLI optionally bootstraps a framework Application via `bootstrap/app.py`

**Originally**: ADR-123 · Date: 2026-05-19

### Context

After WI-020, `ConsoleServiceProvider` exists and `arvel.console.Application.run()` can dispatch a command in-process. But neither was reachable from the `arvel` CLI script. `arvel.console.entrypoint.main()` only knew about entry-point-discovered commands — it never instantiated the framework `arvel.application.Application`. So three categories of commands were stuck:

1. **Queue commands** (`queue:work`, `queue:failed`, `queue:retry`, `queue:flush`, `queue:forget`) need a `QueueManager` from DI. Today they aren't registered at all.
2. **Scheduler commands** (`schedule:work`, `schedule:list`) need the user's `Schedule` (typically wired in `app/console/kernel.py::Kernel.schedule()`). Today they build a fresh empty `Schedule()` and the user's tasks are invisible.
3. **Shell command** needs `app`, `container`, and the facade set in the REPL namespace. Today it returns `{"sys": sys}`.

The unifying root cause: the `arvel` CLI never bootstraps a framework `Application`, so its commands have no container to pull from. Three approaches were considered.

#### Options

**Option 1 — Always bootstrap.** Every `arvel <anything>` invocation calls `bootstrap_framework_application()`. Pro: simple, uniform. Con: startup latency for `arvel --help`, `arvel about`, and every `arvel make:*` invocation — all of which work fine without a container. Hits NFR-021-03 (≤1.0s warm `arvel --help`) immediately because the user's `bootstrap/app.py` may import every provider and run every `register()`.

**Option 2 — Bootstrap on demand via a wrapper script.** Add a separate `arvel-app` binary that bootstraps; keep `arvel` as the plain Typer dispatcher. Pro: clear separation. Con: doubles the user-facing CLI surface (Laravel devs expect one `arvel`/`artisan`); confusing migration story; every doc page would have to explain when to use which binary.

**Option 3 — Lazy opt-in via class marker.** Commands that need a container declare `needs_application: ClassVar[bool] = True`. The entrypoint checks the matched command before bootstrap, only bootstraps when at least one registered (and-about-to-be-invoked) command opts in. Pro: zero overhead for the common help/about/make:* paths; explicit opt-in is type-checkable; integrates cleanly with WI-020's `ConsoleServiceProvider`. Con: two-kinds-of-command in the class hierarchy.

### Decision

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

### Consequences

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

### Implementation notes

- Discovery walks up `_MAX_ANCESTOR_DEPTH = 4` parents of cwd. Configurable later via env var if monorepo needs grow beyond this.
- `bootstrap_framework_application()` propagates `ImportError` from the user's `bootstrap/app.py` — the user wants to see that traceback, not have it swallowed.
- The merge logic uses a dict by `Command.name` for O(1) collision detection; container commands replace entry-point ones in the order: entry-points first, container second (last-write-wins → container wins).
- Tests cover: no `bootstrap/app.py` (returns None), valid `bootstrap/app.py` (returns Application), broken `bootstrap/app.py` (propagates ImportError), nested cwd (walks ancestors up to 4 levels), missing `create_application` (logs warning + returns None).

---

## § 4 — `Command` / `Context` I/O surface: ship the minimum-viable subset, defer prompts and tables

**Originally**: ADR-124 · Date: 2026-05-19

### Context

The `/review` of CLI implemented features (2026-05-19) compared `arvel.console.Command` and `arvel.console.Context` against Laravel artisan and found a long list of gaps:

| Surface | Today | Laravel artisan |
|---|---|---|
| `Context` write methods | `info`, `error`, `line` | `info`, `error`, `line`, `warn`, `comment`, `alert`, `newLine`, `secret`, `ask`, `confirm`, `choice`, `anticipate`, `table`, `progress` |
| Cross-command invocation | none | `$this->call(name, args)`, `$this->callSilently(name, args)` |
| Argument retrieval | implicit (Typer callback args) | `$this->argument('name')`, `$this->option('flag')` |
| Signal handling | none | `$this->trap(SIGTERM, fn() => ...)` |
| Isolation | none | `implements Isolatable` + automatic mutex |
| Automatic prompting | none | `PromptsForMissingInput` trait |

PRD-021 §3 (Out of scope) explicitly defers the prompt surface, tables, progress bars, signal trap, and isolation to a follow-up WI. The question this ADR resolves: of what remains, what's the MVP that lands in WI-021?

#### Options

**Option 1 — Ship nothing new.** Defer the entire `Context` surface to FB-022. Pro: smallest WI-021 diff. Con: WI-021 implements many commands that legitimately need `warn` (e.g., `migrate:status` warns about pending migrations) and `alert` (e.g., `key:generate` alerts on `--force` overwrite). They'd all use `ctx.error()` (red text on stderr) inappropriately, polluting the semantics for actual errors.

**Option 2 — Ship the full Laravel surface.** Implement everything: prompts, tables, progress bars, signal trap, isolation, etc. Pro: parity with one stroke. Con: doubles the WI-021 scope; prompts in particular need careful TTY-vs-non-TTY behaviour (auto-answer in CI), test infrastructure, and a non-trivial dependency on `prompt-toolkit` or `questionary` for a good UX.

**Option 3 — Ship the non-interactive writes + cross-command call.** Add `warn`, `comment`, `alert`, `newline` to `Context`. Add `Command.call(name, args)` and `Command.call_silently(name, args)` (uses the existing `Application.run()` from WI-020). Skip everything that requires user input or terminal capabilities (prompts, tables, progress bars, trap, isolation). Pro: serves every command shipped in WI-021 without compromising semantics; testable without TTY mocking; small diff (~30 LoC + tests). Con: still leaves a parity gap users will notice.

### Decision

**Option 3 — minimum-viable: ship the non-interactive write surface + cross-command call. Defer prompts, tables, progress bars, signal trap, and isolation to FB-022-003/004/005.**

#### Concrete API surface

`Context` (new methods):

```python
def warn(self, message: str) -> None:
    """Yellow message on stdout (warning, but not an error)."""

def comment(self, message: str) -> None:
    """Dim message on stdout (annotation, less prominent than info)."""

def alert(self, message: str) -> None:
    """Bold red boxed message on stdout (high-attention notice)."""

def newline(self, count: int = 1) -> None:
    """Write `count` blank lines."""
```

ANSI colours: `\033[33m` (yellow) for `warn`, `\033[2m` (dim) for `comment`, `\033[1;31m` (bold red) for `alert`. Box-drawing characters for `alert` with ASCII fallback (`***`) when stdout isn't a TTY (per `sys.stdout.isatty()`).

`Command` (new methods):

```python
def call(self, name: str, args: list[str] | None = None) -> int:
    """Invoke another registered command by name; return its exit code."""

def call_silently(self, name: str, args: list[str] | None = None) -> int:
    """Same as `call` but suppress stdout and stderr."""
```

Both methods delegate to `self.app.container.make(Application).run(name, args)`. When `self.app is None` (command didn't opt into bootstrap OR bootstrap failed), they raise `RuntimeError("Command.call requires a bound framework Application; set needs_application = True on the command class.")`.

### Out of scope (deferred — captured for FB-022)

| Feature | Reason for deferral | Tracking |
|---|---|---|
| `ask`, `confirm`, `choice`, `secret`, `anticipate` | Needs careful TTY-vs-non-TTY behaviour, auto-answer in CI, and a prompt library dependency decision (`prompt_toolkit` vs `questionary` vs roll-your-own) | FB-022-003 |
| `table(headers, rows)` | Wants column-width calculation, alignment, multi-line cell support — substantial implementation; out of WI-021 scope | FB-022-003 |
| `progress(total)` | Same as table; also overlaps with `rich.progress` if we depend on `rich` | FB-022-003 |
| Signal `trap(SIGTERM, ...)` | Useful for queue workers and scheduler — but those work today via `loop.add_signal_handler` directly; the convenience wrapper is nice-to-have | FB-022-004 |
| `implements Isolatable` + mutex | Cross-cutting concern that needs a lock backend decision (file? Redis? DB?). Best delivered together with the lock backend, not bolted onto a single WI | FB-022-005 |
| `PromptsForMissingInput` trait | Depends on the prompt surface (FB-022-003) | FB-022-003 |
| `argument(name)` / `option(name)` retrieval helpers | Typer callback params already provide typed access; helpers would only help when commands implement `handle()` AND want positional/keyword args. Of the WI-021 commands, none need this — `register()`-pattern commands use Typer params directly | FB-022-006 |

### Consequences

**Positive:**

- WI-021's command implementations have semantically-correct write methods (e.g., `migrate:status` uses `warn` for pending, `info` for applied; `key:generate --force` uses `alert` for the destructive-overwrite notice).
- `Command.call()` opens the door for composite commands (e.g., `arvel install:auth` could `self.call("migrate")` + `self.call("db:seed")` once those commands are real).
- Small diff (~30 LoC for `Context` methods + ~15 LoC for `Command.call`/`call_silently` + tests). Doesn't bloat WI-021.

**Negative:**

- Laravel devs comparing parity will see the missing prompts/tables. Mitigated by CHANGELOG explicitly listing the deferred surface with FB-022-003 pointer.
- TWO methods (`warn` and `alert`) overlap visually with `error` if a casual reader squints. Mitigated by docstrings and DXD-021 §4 examples showing the semantic difference.

**Neutral:**

- No new external dependency. All four `Context` methods + both `Command.call*` methods use stdlib only (`sys.stdout.isatty()`, ANSI escapes).
- `Command.call_silently()` uses `contextlib.redirect_stdout` + `redirect_stderr` to a `StringIO` — composes cleanly with `Application.run()`.

### Implementation notes

- ANSI colour escapes are unconditional today. A follow-up could add `NO_COLOR` env var support (standard convention, FB-022-007).
- `Context.alert()`'s box-drawing falls back to `***` when stdout isn't a TTY because Unicode box characters render poorly in CI log viewers (GitHub Actions, GitLab CI).
- Tests use `capsys` to assert escape codes are present in TTY mode and absent in non-TTY (monkeypatch `sys.stdout.isatty` to return False).
- `Command.call_silently()`'s suppression is best-effort: if the invoked command writes directly to `sys.stderr` via `os.write(2, ...)` or similar, that bypass is not caught. Documented as "captures Python-level writes; subprocess output is the caller's responsibility."

---

## § 5 — Stub-template ownership in `make:*` commands

**Originally**: ADR-125 · Date: 2026-05-19

### Context

`BaseMakeCommand` currently generates a single generic stub (`class <Name>: pass`) for all `make:*` commands. WI-023 introduces 13 new generators and improves 11 existing ones; users expect each generator to produce framework-aware boilerplate (e.g., `make:controller` should generate a class extending `Controller` with a sample handler).

We had three options:

1. **Per-command override of `_render(name)`** — each subclass owns its template inline.
2. **Template files on disk** — load `.tmpl` files via package data.
3. **Single template engine** — one rendering function that branches by command type.

### Decision

Each `make:*` subclass owns its own `_render(name)` method, returning the stub as a Python string. The base class keeps a fallback (`class <Name>: pass`) but every subclass overrides it.

### Rationale

| Aspect | Per-command override | Template files | Single engine |
|---|---|---|---|
| Type-checked | ✓ | ✗ (strings) | ✗ |
| Co-located with command | ✓ | ✗ (separate dir) | ✗ |
| Testable | ✓ | ✓ | ✓ |
| No package-data complexity | ✓ | ✗ (need `importlib.resources` per stub) | ✓ |
| Easy to add new commands | ✓ (one new file) | ✗ (two: command + template) | ✗ (modify central engine) |
| Easy to add new placeholders | scoped to one command | ✗ (template knows nothing about Python types) | ✗ |

**Per-command override wins** because:

1. Templates are small (typically 10-15 lines). Inline strings stay readable.
2. The template lives next to the command that produces it — easy to locate, easy to test together.
3. Adding a new generator is one new module, no template-file/manifest sync issues.
4. Static type-checking sees the template as code, catching f-string bugs at lint time.

### Consequences

#### Positive

- One command per file; template + behavior co-located.
- No `importlib.resources` boilerplate or `MANIFEST.in` updates needed when adding generators.
- Stub renderings can use computed values (timestamps, class names, plural forms) naturally.

#### Negative

- Multi-line Python strings have to be carefully formatted. Mitigated by writing tests that snapshot the rendered output (one `tests/console/test_make_stubs.py` per command cluster).

### Alternatives rejected

- **Template files on disk**: requires `MANIFEST.in` and `importlib.resources` plumbing for every generator. Real complexity, no real upside for templates this small.
- **Jinja or other template engine**: massive overkill. We don't need conditionals or loops in stub generation; concatenated f-strings work.

### Implementation notes

- Each subclass overrides `_render(self, name: str) -> str`.
- `_target_subdir` (existing class attribute) determines the output directory.
- For commands that produce timestamped filenames (e.g., `make:migration`), the subclass also overrides `_target_path(self, name: str) -> Path`.
- The base class `_render()` becomes a one-line fallback; if a subclass forgets to override it, the bug is obvious in the generated file.

---

## § 6 — Consolidate the CLI into a single `arvel` binary (delete `arvel-cli`)

**Originally**: ADR-126 · Date: 2026-05-20

### Context

ADR-017 § 6 picked a two-binary split to resolve the `[project.scripts] arvel` collision between `packages/arvel` (framework CLI) and `packages/arvel-cli` (scaffolder). The framework kept `arvel`; the scaffolder was renamed to `arvel-new` and shipped from a separate PyPI distribution.

A few months in, the two-binary split is paying negative dividends:

- Users have to install **two** things (`uv tool install arvel-cli` for the scaffolder, then `arvel` arrives transitively when they `uv sync` inside the project).the docs (`installation.md`, `starter-kits.md`, every "getting started" page), and the badges (two PyPI badges in the README).
- The scaffolder duplicates infrastructure the framework already has: name validation, templating, Typer wiring, an `Application` shell — without sharing types or tests with the framework.
- The release pipeline carries two parallel tracks: two `release-please` components, two PyPI Trusted Publishers, two SBOMs, two CycloneDX exports, two `uv build` invocations, two `twine check` calls.
- Users discover `arvel-new` only through docs. Once they're inside a project, `arvel` is the entry point — `arvel-new` is no longer needed and clutters their `~/.local/bin`.
- The framework already gates its in-project commands behind `find_project_root()` (ADR-017 § 3). Allowing one more name (`new`) in the outside-project allow-list and registering it as an entry-point is a one-line change.

The scaffolder is a single Typer command (`new`) with three flags (`--no-install`, `--python`, `--help`). Carrying a dedicated package for that is the smallest unit of complexity, but it's still complexity. Cutting it out is a net subtraction.

#### Options reconsidered

**Approach A — Move `arvel-cli` source into `packages/arvel/`, keep the separate distribution.** Same two PyPI packages, but `arvel-cli` becomes a thin wheel that depends on `arvel` and re-exports a Typer command. Pro: zero install-side change. Con: keeps every downside above (two release tracks, two SBOMs, two installs) and adds a circular concern (the scaffolder now imports from the framework it scaffolds).

**Approach B — Merge into a single `arvel` package.** Move the scaffolder's source, skeleton tree, and tests into `packages/arvel/`. Register `new` as a `[project.entry-points."arvel.commands"]` entry. Allow-list it in the outside-project gate. Delete `packages/arvel-cli/`. **(chosen)**

**Approach C — Keep two packages, leave the rename in place.** Status quo. Rejected: same downsides, no upsides.

### Decision

**Approach B.** Consolidate everything the user installs and runs into the single `arvel` PyPI package.

#### Concrete changes

- **Sources moved**
  - `packages/arvel-cli/src/arvel_cli/_templating.py` → `packages/arvel/src/arvel/console/_scaffold/templating.py`
  - `packages/arvel-cli/src/arvel_cli/_validation.py` → `packages/arvel/src/arvel/console/_scaffold/validation.py`
  - `packages/arvel-cli/src/arvel_cli/skeleton/` → `packages/arvel/src/arvel/_skeleton/`
  - `packages/arvel-cli/src/arvel_cli/cli.py` → `packages/arvel/src/arvel/console/commands/new.py` (rewritten as an `arvel.console.Command` subclass; the Typer wiring matches the rest of the make:* commands)
- **New entry-point**
  ```toml
  [project.entry-points."arvel.commands"]
  "new" = "arvel.console.commands.new:NewCommand"
  ```
- **Outside-project allow-list** — `_OUTSIDE_PROJECT_ALLOWED_NAMES` in `arvel.console.entrypoint` now includes `"new"`. The migration hint message points at `arvel new` (one binary, one command).
- **Stale skeleton shim removed** — `packages/arvel/src/arvel/_skeleton/arvel` (the pre-WI-005 console-shim file) is deleted. The real `arvel` binary on the user's PATH supersedes it.
- **Tests** — moved to `packages/arvel/tests/console/scaffold/`. The two arvel-cli-only tests (`test_script_rename.py`, `test_smoke.py`) were obsolete after the merge and removed.
- **Package deleted** — `packages/arvel-cli/` is gone.
- **Workspace + tooling** — `tool.uv.workspace` (root `pyproject.toml`), `[tool.mypy]` paths/files, `[tool.pyright]` includes/extraPaths, `[tool.pytest.ini_options].testpaths`, `Makefile` `SRC` / `sbom` / `build` targets, and every CI workflow (`ci.yml`, `security.yml`, `release-please.yml`, `publish.yml`, `release-please-config.json`, `release-please-manifest.json`) all drop the `arvel-cli` track.
- **Installers** — `install.sh` and `install.ps1` install `arvel` (instead of `arvel-cli`). The "next steps" line is `arvel new my-app`.
- **Docs** — `installation.md`, `starter-kits.md`, `structure.md`, `artisan.md`, `releases.md`, `contributions.md`, `sail.md`, `pint.md`, `homestead.md`, `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `docs/ops/README.md` all switched from the two-binary story (`arvel-cli` + `arvel-new`) to one-binary (`arvel new`).

#### Consequences

**Positive**

- One install (`uv tool install arvel`), one binary, one mental model.
- Half as many wheels, SBOMs, release components, and CI jobs.
- Scaffolding shares the same `Command` machinery, name validator, and test harness as the rest of the CLI — no duplication.
- Bug-fix flow is shorter — one `pip install --upgrade arvel` updates both scaffolder and framework.

**Negative**

- Anyone who installed `arvel-cli` before this ADR has to uninstall it (`uv tool uninstall arvel-cli`) and install `arvel` instead. The `no-backward-compatibility.mdc` rule says no legacy aliases — there is no `arvel-new` shim. The migration is one paragraph in the changelog.
- Users coming from ADR-017 § 6-era docs need to retrain their fingers: `arvel new my-app` (with a space) replaces `arvel-new my-app`.

**Neutral**

- The packaged skeleton lives inside the framework's wheel via `importlib.resources.files("arvel").joinpath("_skeleton")`. Hatchling's default `[tool.hatch.build.targets.wheel].packages = ["src/arvel"]` includes the whole tree, so the skeleton ships untouched.

#### Verification

End-to-end smoke test after the merge:

```bash
uv sync
uv run arvel --help                 # shows `new` alongside `migrate`, `route:list`, …
uv run arvel new test-app --no-install
cd test-app
uv sync
uv run arvel make:model Post       # in-project make: works
uv run arvel about                 # framework facts
```

All quality gates run clean: `make ci`, `make security`, plus the migrated `tests/console/scaffold/` suite.

### References

- ADR-001 § 5 — canonical app layout (the skeleton is the on-disk shape of this ADR)
- ADR-017 § 1 — CLI packaging (replaced by this ADR for the "where does the scaffolder live" question)
- ADR-017 § 3 — CLI framework bootstrap (the outside-project gate that `new` plugs into)
- ADR-017 § 6 — the two-binary split, now superseded by this ADR
- `packages/arvel/src/arvel/console/commands/new.py` — the new command
- `packages/arvel/src/arvel/_skeleton/` — the packaged project skeleton

---

### Merged: Resolve the `arvel` console-script collision: rename `arvel-cli`'s script to `arvel-new` (was ADR-017 § 6)

**Status**: Superseded
**Date**: 2026-05-19
**Supersedes**: none
**Superseded by**: [ADR-017 § 6](ADR-017-console.md)
**Related**: ADR-017 § 3 (CLI framework bootstrap), `packages/arvel-cli/pyproject.toml`

### Context

Two packages each declare a `[project.scripts]` entry named `arvel`:

- `packages/arvel/pyproject.toml` → `arvel = "arvel.console.entrypoint:main"` (the framework binary).
- `packages/arvel-cli/pyproject.toml` → `arvel = "arvel_cli.cli:main"` (the scaffolder, used as `arvel new my-app`).

When a user runs `pip install arvel arvel-cli`, whichever wheel installs the script last wins. The user ends up with EITHER the scaffolder OR the framework — not both. The other binary is silently replaced. Even worse, the failure mode is invisible until the user tries to run `arvel migrate` and gets "command not found" or "scaffolder-like behaviour".

Three approaches were considered.

#### Options

**Option 1 — Single binary with subcommand routing.** Make `arvel` always be the framework's entrypoint; merge the scaffolder's `new` subcommand into the framework as a built-in. Pro: one binary, one mental model — closest to Laravel's `composer create-project` + `php artisan` split (where `composer` is a separate tool). Con: makes `arvel-cli` a dev-dependency of `arvel`, inverting today's dep direction; muddies the scaffolder/framework boundary that Article XI explicitly draws.

**Option 2 — Rename `arvel-cli`'s script to `arvel-new`.** Adjust `packages/arvel-cli/pyproject.toml` to `arvel-new = "arvel_cli.cli:main"`. Pro: clean separation maintained; install order doesn't matter; users run `arvel-new my-app` to scaffold and `arvel <whatever>` inside the project. Con: existing users with muscle memory for `arvel new` must update aliases/docs.

**Option 3 — Console-script-with-namespace** (e.g., `arvel cli new` invokes scaffolder). Pro: keeps "arvel" as the only binary. Con: requires the framework's `arvel` to know about the scaffolder, or vice versa; same coupling problem as Option 1 with extra indirection.

### Decision

**Option 2 — rename `arvel-cli`'s console script to `arvel-new`** AND add an outside-project wrapper inside the framework's `arvel` script that detects when the user is running commands outside a project directory.

#### Concrete change

`packages/arvel-cli/pyproject.toml`:

```toml
[project.scripts]
## WI-021: renamed from "arvel" to "arvel-new" to resolve console-script collision with the
## framework's "arvel" binary. See ADR-017 § 6.
arvel-new = "arvel_cli.cli:main"
```

The framework's `arvel` script (`arvel.console.entrypoint:main`) detects when it's run outside a project (no `bootstrap/app.py` in cwd-or-up-to-4-ancestors per ADR-017 § 3) AND the requested subcommand isn't in the "always allowed" set (`--help`, `--version`, `about`, `make:*`, `key:generate`). When that happens, it prints:

```
No Arvel project found. To create a new project:
  arvel-new <name>   (install: pip install arvel-cli)
To run a command outside a project, use arvel make:* or arvel about.
```

…and exits 2. This gives a user who runs `arvel migrate` outside a project a discoverable migration path to the new command name without them having to read release notes.

#### Install scripts and skeleton docs

`scripts/install.sh`, `scripts/install.ps1`, the scaffolder skeleton's `README.md.tmpl`, and `docs/strategy/constitution.md` references all switch to `arvel-new` for any example invocations of the scaffolder.

### Consequences

**Positive:**

- `pip install arvel arvel-cli` works regardless of install order — both binaries are reachable.
- Clean separation between scaffolder (`arvel-new`, lives in `packages/arvel-cli`) and framework (`arvel`, lives in `packages/arvel`).
- Outside-project wrapper gives existing `arvel new` users a clear, discoverable migration path.
- No coupling between framework and scaffolder beyond what already exists (skeleton's `Makefile` references `arvel` — that doesn't change; `arvel-new` only ever runs at scaffold time).

**Negative:**

- BREAKING for any user / CI script / shell alias that referenced `arvel new` (the scaffolder). CHANGELOG marks the WI-021 commit with the Conventional Commits `!` suffix and includes a migration line in the Unreleased section.
- One new gate added to `docs/dx/quality-gates.md` (#33 dual-install matrix CI job) to prevent future regression — CI fails if either binary becomes unreachable in either install order.

**Neutral:**

- The framework's `arvel` script binary path is unchanged; only its "outside project" behaviour is new.
- The naming `arvel-new` mirrors `create-react-app` / `create-vite-app` conventions familiar to JS devs and is short enough to type. Considered alternatives: `arvel-scaffold`, `arvel-init`, `mkarvel` — rejected for being longer or less discoverable.

### Implementation notes

- Test fixture in `packages/arvel-cli/tests/test_script_rename.py` asserts `which arvel-new` resolves after `uv pip install ./packages/arvel-cli` and that `which arvel` does NOT point to the scaffolder.
- Dual-install matrix CI job runs in fresh venvs, both `framework-first` and `scaffolder-first` orderings, asserting `arvel --version && arvel-new --help` both exit 0 (NFR-021-05).
- Constitution amendment NOT required — Article XI ("Scaffolder vs framework") already mandates separation; this ADR just makes the script names reflect the separation that was always intended.

---

## Subsumes

This ADR absorbs the following ADRs in the WI-arvel-005 consolidation pass (2026-06-07). The original files are deleted; their decision text is preserved verbatim above in the corresponding `§` sections.

| Old | Date | Subject | New location |
|---|---|---|---|
| ADR-121 | 2026-05-17 | `arvel-cli` packaging strategy | § 1 |
| ADR-122 | 2026-05-17 | Typer Single-Command Promotion Workaround | § 2 |
| ADR-123 | 2026-05-19 | CLI optionally bootstraps a framework Application via `bootstrap/app.py` | § 3 |
| ADR-124 | 2026-05-19 | `Command` / `Context` I/O surface: ship the minimum-viable subset, defer prompts and tables | § 4 |
| ADR-125 | 2026-05-19 | Stub-template ownership in `make:*` commands | § 5 |
| ADR-126 | 2026-05-20 | Consolidate the CLI into a single `arvel` binary (delete `arvel-cli`) | § 6 |
