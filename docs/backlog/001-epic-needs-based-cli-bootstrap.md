# Epic: Needs-based CLI bootstrap

## Summary

Replace the current "boot everything inside a project" CLI lifecycle with a needs-based bootstrap: each `Command` declares which subsystems it requires; each `ServiceProvider` declares which subsystem it serves; the entrypoint registers and boots only the providers a command actually needs. As part of the rewrite, fix `openapi:export --output` so it accepts paths outside the project root and emits framework chatter on stderr so the banner stays clean.

This is a greenfield rewrite — no backward-compatibility shims. `Command.needs_application` is replaced; the `_safe_output_path` restriction is removed; the new `requires` machinery is the only path.

## Design reference

`docs/plans/2026-06-05-needs-based-cli-bootstrap-design.md`

## Stories

### Story 1: Define `CliSubsystem` enum and dependency graph

**As a** framework developer, **I want** a single typed enum naming every subsystem a CLI command may need, **so that** commands and providers refer to the same vocabulary and the bootstrap can compute transitive dependencies mechanically.

**Acceptance Criteria**:

- [ ] Given the new module `arvel/console/_subsystem.py`, when I import `CliSubsystem`, then I get a `StrEnum` containing at least `CONFIG`, `LOG`, `LANG`, `CONTEXT`, `OBSERVABILITY`, `DATABASE`, `HTTP`, `SCHEDULER`, `QUEUE`, `CACHE`, `MAIL`, `STORAGE`, `BROADCAST`, `AUTH`, `EVENTS`, `USER_PROVIDERS`.
- [ ] Given the same module, when I import `FOUNDATION_SUBSYSTEMS`, then I get a `frozenset` containing `CONFIG`, `LOG`, `LANG`, `CONTEXT` and nothing else.
- [ ] Given the same module, when I call `closure({CliSubsystem.QUEUE})`, then the result contains `QUEUE` and `DATABASE`.
- [ ] Given the same module, when I call `closure({CliSubsystem.AUTH})`, then the result contains `AUTH` and `DATABASE`.
- [ ] Given a cyclic dependency in the graph, when the module imports, then it raises at import time with a clear message naming the cycle.
- [ ] Given `closure(frozenset())`, then it returns `frozenset()` (no implicit foundation injection — that's the bootstrap's job).

**Security Requirements**:

- [ ] None — pure typed-data module, no I/O.

**Documentation Requirements**:

- [ ] One short module docstring explaining what a subsystem is and how to add one.

**Requirement Refs**: NEW (no prior PRD)
**Priority**: Must
**Complexity**: Small
**Status**: Ready

---

### Story 2: Tag built-in providers with their subsystem

**As a** framework developer, **I want** every shipped `ServiceProvider` subclass to advertise its `CliSubsystem`, **so that** the bootstrap can filter the provider chain by command needs.

**Acceptance Criteria**:

- [ ] Given `arvel.providers.ServiceProvider`, when I read its class body, then `subsystem: ClassVar[CliSubsystem | None] = None`.
- [ ] Given each baseline-head provider (`ConfigServiceProvider`, `LogServiceProvider`, `LangServiceProvider`, `ContextServiceProvider`, `DatabaseServiceProvider`, `HttpServiceProvider`, `SchedulerServiceProvider`, `ObservabilityServiceProvider`), when I read its class body, then `subsystem` matches the design matrix (e.g., `HttpServiceProvider.subsystem == CliSubsystem.HTTP`).
- [ ] Given `ConsoleServiceProvider`, when I read its class body, then `subsystem is None` (foundation; always last).
- [ ] Given every framework-shipped optional provider (`CacheServiceProvider`, `QueueServiceProvider`, `MailServiceProvider`, `StorageServiceProvider`, `BroadcastServiceProvider`, `AuthServiceProvider`, `EventServiceProvider`), when I read its class body, then `subsystem` matches the design matrix.
- [ ] Given a user provider (e.g., a project's `AppServiceProvider`) that omits `subsystem`, when it's loaded by `_load_providers_from_path`, then it defaults to `CliSubsystem.USER_PROVIDERS` (the loader assigns the default if the class doesn't override it).
- [ ] Given a regression test, when it walks `arvel.providers`, then every shipped provider has a `subsystem` attribute set explicitly (no implicit `None` except for `ServiceProvider` itself and `ConsoleServiceProvider`).

**Security Requirements**:

- [ ] None.

**Documentation Requirements**:

- [ ] Update `docs/architecture/service-providers.md` to document the `subsystem` ClassVar and the user-provider default.

**Requirement Refs**: NEW
**Priority**: Must
**Complexity**: Medium
**Status**: Ready

---

### Story 3: Replace `Command.needs_application` with declarative `Command.requires`

**As a** command author, **I want** to declare what my command needs as a `frozenset[CliSubsystem]`, **so that** the CLI only boots what I actually use.

**Acceptance Criteria**:

- [ ] Given `arvel.console.Command`, when I read its class body, then `needs_application: ClassVar[bool]` is removed and replaced with `requires: ClassVar[frozenset[CliSubsystem]] = frozenset()`.
- [ ] Given `arvel.console.Command`, when I read its class body, then `requires_project_context: ClassVar[bool] = False` is added (separate, cheap flag for commands like `serve` that need a project root but no boot).
- [ ] Given any `Command` subclass with non-empty `requires`, when the CLI dispatches it, then `self.app` is bound to the booted `FrameworkApplication`.
- [ ] Given any `Command` subclass with empty `requires` and `requires_project_context = False`, when the CLI dispatches it, then `self.app is None`.
- [ ] Given a command whose `requires` contains a `CliSubsystem` member, when a type-checker (`mypy --strict`) runs over the file, then it passes with no errors.
- [ ] Given a command that incorrectly assigns a non-`CliSubsystem` value to `requires`, when the type-checker runs, then it fails (the type is `frozenset[CliSubsystem]`, not `frozenset[str]`).
- [ ] Given `Command.call(name, args)`, when called from a command that has a bound `self.app`, then it still works (no behaviour change beyond the bound-app contract).

**Security Requirements**:

- [ ] None — pure refactor of the contract.

**Documentation Requirements**:

- [ ] Update `docs/console/cli-architecture.md` "The Command base" section with the new fields and remove `needs_application` references.

**Requirement Refs**: NEW
**Priority**: Must
**Complexity**: Small
**Status**: Ready

---

### Story 4: Implement selective bootstrap in the entrypoint

**As a** CLI user, **I want** `arvel <command>` to boot only the subsystems that command needs, **so that** generators don't pay for a database ping and unrelated provider connect calls.

**Acceptance Criteria**:

- [ ] Given a new module `arvel/console/_boot_plan.py`, when I import `BootPlan`, then I get a frozen dataclass with `required_subsystems: frozenset[CliSubsystem]`, `needs_project: bool`, `needs_framework: bool`.
- [ ] Given the same module, when I call `plan_bootstrap(command_name)` for a command with empty `requires`, then `BootPlan.needs_framework is False`.
- [ ] Given the same module, when I call `plan_bootstrap("migrate")`, then `BootPlan.required_subsystems == FOUNDATION_SUBSYSTEMS | {CliSubsystem.DATABASE}`.
- [ ] Given the same module, when I call `plan_bootstrap("queue:work")`, then `BootPlan.required_subsystems` includes `QUEUE`, `DATABASE`, `USER_PROVIDERS`, and the foundation set.
- [ ] Given the same module, when I call `plan_bootstrap(None)` (no command, e.g., `arvel` / `arvel --help`), then `BootPlan.needs_framework is False`.
- [ ] Given `Application._resolve_provider_chain`, when called with a `required_subsystems` argument, then it returns only providers whose `subsystem` is `None` or in the set (USER_PROVIDERS bucket honored), preserving HEAD → user → TAIL order.
- [ ] Given `async_main(project_root, command, plan)`, when `plan.needs_framework is False` and `plan.needs_project is False`, then it does NOT call `bootstrap_framework_application` or `boot()`/`shutdown()` — it just dispatches.
- [ ] Given `arvel make:controller Foo` run inside the e-commerce kit, when I trace it, then `DatabaseServiceProvider.boot` is NEVER called.
- [ ] Given `arvel migrate` run inside the same kit, when I trace it, then `QueueServiceProvider.boot`, `MailServiceProvider.boot`, `BroadcastServiceProvider.boot`, `StorageServiceProvider.boot`, `CacheServiceProvider.boot`, `SchedulerServiceProvider.boot` are NEVER called; `DatabaseServiceProvider.boot` IS called.
- [ ] Given `arvel <unknown>`, when run, then no provider boots and Typer prints "no such command" with exit code 2.
- [ ] Given a command that fails after partial boot, when the finally-block runs, then `shutdown()` is called only on providers that successfully booted (no `AttributeError` on uninitialised resources).

**Security Requirements**:

- [ ] None — same trust model as today; the bootstrap still loads `bootstrap/app.py` verbatim when the command needs it.

**Documentation Requirements**:

- [ ] Update `docs/console/cli-architecture.md` "Bootstrap for the CLI" section with the new flow diagram (replace the current Mermaid chart).

**Requirement Refs**: NEW
**Priority**: Must
**Complexity**: Large
**Status**: Ready

**Dependencies**: Stories 1, 2, 3.

---

### Story 5: Migrate every built-in command to declare `requires`

**As a** maintainer, **I want** every command shipped under `arvel/console/commands/` and inside provider `commands()` methods to set its `requires` per the design matrix, **so that** the new bootstrap actually filters anything.

**Acceptance Criteria**:

- [ ] Given each `make:*` command and `new`, `about`, `key:generate`, when I read its class body, then `requires = frozenset()`.
- [ ] Given each command in the design matrix (Section 5), when I read its class body, then `requires` matches the table exactly.
- [ ] Given the queue commands (`queue:work`, `queue:failed`, …) registered by `QueueServiceProvider.commands()`, when I read them, then each has `requires = frozenset({CliSubsystem.QUEUE, CliSubsystem.USER_PROVIDERS})`.
- [ ] Given the scheduler commands registered by `SchedulerServiceProvider.commands()`, when I read them, then each has `requires = frozenset({CliSubsystem.SCHEDULER, CliSubsystem.USER_PROVIDERS})`.
- [ ] Given `ServeCommand`, when I read it, then `requires = frozenset()`, `requires_project_context = True`, `owns_process = True`.
- [ ] Given `ShellCommand` and `TinkerCommand`, when I read them, then `requires` is the full set of every non-foundation subsystem plus `USER_PROVIDERS`.
- [ ] Given the existing console test suite (`packages/arvel/tests/console/`), when it runs against the new code, then every prior `needs_application=True` assertion is replaced by an equivalent `requires`-based assertion (tests are rewritten, not adapted).
- [ ] Given any command in any package (`arvel-audit`, `arvel-image`, `arvel-oauth`, `arvel-permission`, `arvel-search`) inside the workspace, when I grep for `needs_application`, then there are zero hits.

**Security Requirements**:

- [ ] None.

**Documentation Requirements**:

- [ ] Update the per-command catalog in `docs/site/docs/cli/commands.md` to note which subsystems each command boots (a single column added to the existing tables).

**Requirement Refs**: NEW
**Priority**: Must
**Complexity**: Medium
**Status**: Ready

**Dependencies**: Stories 1, 2, 3, 4.

---

### Story 6: `openapi:export --output` accepts any path; status goes to stderr

**As a** CI/Makefile user, **I want** `arvel openapi:export --output <anywhere>` to write the spec to an absolute or sibling path without falling back to `--stdout` redirection, **so that** the banner and status messages stay on stderr and never pollute the spec.

**Acceptance Criteria**:

- [ ] Given `arvel openapi:export --output /tmp/spec.yaml --format yaml`, when run inside a project, then the file is written to `/tmp/spec.yaml` and the command exits 0.
- [ ] Given `arvel openapi:export --output ../frontend/openapi.yaml --format yaml`, when run inside `kits/arvel-ecommerce-kit/backend/`, then the file is written to `kits/arvel-ecommerce-kit/frontend/openapi.yaml`.
- [ ] Given `arvel openapi:export --output ./docs/api/openapi.yaml` (relative path), when run, then the file is resolved against the current working directory (NOT the project root) — relative semantics match `git`/`make`/`cp` conventions.
- [ ] Given the same command, when its parent directory does not exist, then the command creates it with `parents=True, exist_ok=True` and writes the file.
- [ ] Given `arvel openapi:export --output -`, when run, then the spec is emitted on stdout (POSIX `-` convention; equivalent to `--stdout`).
- [ ] Given `arvel openapi:export --stdout` and `arvel openapi:export --output -`, when both run with the same `--format`, then the stdout output is byte-identical.
- [ ] Given `arvel openapi:export --output spec.yaml`, when run successfully, then the line `OpenAPI spec written to <path>` is written to **stderr** (was stdout).
- [ ] Given `arvel openapi:export --stdout > captured.yaml`, when run, then `captured.yaml` contains only the spec — no banner, no status — and the banner appears on the user's terminal (stderr) as today.
- [ ] Given `arvel openapi:export --output ../frontend/openapi.yaml --no-banner`, when run in a script, then the file is the only output produced; stdout and stderr are empty (or carry only errors).
- [ ] Given the existing `_safe_output_path` helper, when the new code lands, then it is removed (no path-traversal restriction remains).
- [ ] Given that the command runs an OpenAPI build internally, when the build fails, then the error message goes to stderr and exit code is 1 (or 2 for missing `pyyaml`); no partial file is left behind.
- [ ] Given `arvel openapi:export --output -- --format yaml` (lone `--` between flags), the existing Typer/Click parsing handles it; the command does not treat `--` as a filename.
- [ ] Given the kit Makefile target `api-generate`, when it switches to `arvel openapi:export --output ../frontend/openapi.yaml --format yaml`, then `make api-generate` produces the same `frontend/openapi.yaml` content as before with no shell redirection.

**Security Requirements**:

- [ ] No path-traversal validation. The CLI invoker is trusted to choose the output path (same trust level as `cp`, `mv`).
- [ ] The command does NOT follow symlinks during the write step (uses `Path.write_text` which creates a regular file; preexisting symlinks at the target are overwritten as their target). This matches the current behavior.

**Documentation Requirements**:

- [ ] Update `docs/site/docs/cli/commands.md` for `openapi:export` (note `--output` accepts any path, status on stderr, `--output -` sugar).
- [ ] Update the e-commerce kit Makefile docs in `kits/arvel-ecommerce-kit/README.md` if `api-generate` is mentioned.

**Requirement Refs**: NEW
**Priority**: Must
**Complexity**: Small
**Status**: Ready

**Dependencies**: None (independent of Stories 1–5; can ship in any order, but landed in the same WI for review locality).

---

### Story 7: Update CLI architecture documentation

**As a** new contributor, **I want** `docs/console/cli-architecture.md` and `docs/site/docs/cli/commands.md` to reflect the needs-based bootstrap accurately, **so that** the docs describe the system as it ships, not as it used to be.

**Acceptance Criteria**:

- [ ] Given `docs/console/cli-architecture.md`, when I read it, then every reference to `needs_application` is gone, replaced by `requires` and `requires_project_context`.
- [ ] Given the same file, when I read the Mermaid flow, then it shows the `plan_bootstrap` decision point, the filtered provider chain, and the bullet for "foundation always loads".
- [ ] Given the same file, when I read the catalog section, then it lists each command group with its subsystem requirements (single new column).
- [ ] Given `docs/site/docs/cli/commands.md`, when I read each command's row, then a new "Boots" column shows the subsystems (e.g., "Database", "HTTP + User providers", "—" for pure generators).
- [ ] Given `docs/architecture/service-providers.md`, when I read it, then the `subsystem` ClassVar is documented with the user-provider default rule.
- [ ] Given the existing markdown lint config, when CI runs against the updated docs, then it passes (no broken links, no orphan headings).

**Security Requirements**:

- [ ] None.

**Documentation Requirements**:

- [ ] This story IS the documentation work.

**Requirement Refs**: NEW
**Priority**: Should
**Complexity**: Small
**Status**: Ready

**Dependencies**: Stories 1–6.

---

### Story 8: Cold-start benchmark guards the regression

**As a** maintainer, **I want** a benchmark that asserts cold-start times for representative commands stay under defined thresholds, **so that** a future change can't quietly bring back the "boot everything" cost.

**Acceptance Criteria**:

- [ ] Given `benchmarks/cli_cold_start_bench.py`, when run via `pytest-benchmark` against the e-commerce kit, then it exercises at least `arvel about`, `arvel make:controller Foo --force`, `arvel migrate --dry-run`, `arvel openapi:export --output /tmp/spec.yaml`.
- [ ] Given each benchmarked command, when its median wall-clock is computed, then it falls under the design target (`about`: <0.3s; `make:controller`: <0.5s; `migrate --dry-run`: <1.5s; `openapi:export`: <2.5s) on the CI runner; thresholds are configured in the bench file with a tolerance band.
- [ ] Given a CI workflow `.github/workflows/cli-cold-start.yml` (or addition to an existing workflow), when it runs on PR, then a regression beyond the tolerance fails the job with a clear message ("`arvel migrate` cold-start exceeded 1.5s threshold by X%").
- [ ] Given the benchmark module, when run repeatedly, then it never connects to a real external service (uses the kit's local SQLite/Redis stubs).

**Security Requirements**:

- [ ] None.

**Documentation Requirements**:

- [ ] Short README inside `benchmarks/` explaining how to run the bench locally and how to refresh thresholds.

**Requirement Refs**: NEW
**Priority**: Should
**Complexity**: Medium
**Status**: Ready

**Dependencies**: Stories 1–5.

---

### Story 9: Plug-in provider compatibility check

**As a** plug-in author (`arvel-audit`, `arvel-image`, `arvel-oauth`, `arvel-permission`, `arvel-search`), **I want** clear guidance on tagging my provider with a `CliSubsystem`, **so that** my commands work under the needs-based bootstrap.

**Acceptance Criteria**:

- [ ] Given each in-tree plug-in package, when I read its provider class, then either `subsystem` is set explicitly to an appropriate `CliSubsystem` or the loader assigns `USER_PROVIDERS` (the default for "anything not a baseline framework subsystem").
- [ ] Given each in-tree plug-in's commands (e.g., `arvel_audit.commands.install`), when I read them, then their `requires` is set per their actual needs (most plug-in commands need `USER_PROVIDERS` to surface their provider; some need `DATABASE` for install/migrate flows).
- [ ] Given the existing plug-in test suites, when they run against the new code, then they pass with no new failures attributable to the bootstrap change.
- [ ] Given `docs/architecture/service-providers.md` "Authoring a provider" section, when I read it, then it tells me which `CliSubsystem` to pick (or to use the `USER_PROVIDERS` default) and how to declare command `requires`.

**Security Requirements**:

- [ ] None.

**Documentation Requirements**:

- [ ] Plug-in authoring section in `docs/architecture/service-providers.md`.

**Requirement Refs**: NEW
**Priority**: Should
**Complexity**: Medium
**Status**: Ready

**Dependencies**: Stories 1–5.

---

### Story 10: Remove `needs_application` and `_safe_output_path` from the codebase

**As a** code reviewer, **I want** confirmation that no dead code from the old bootstrap survives, **so that** the rewrite is clean and audit-friendly.

**Acceptance Criteria**:

- [ ] Given a workspace-wide grep, when I search for `needs_application`, then there are zero hits outside historical CHANGELOG entries.
- [ ] Given the same grep for `_safe_output_path`, then there are zero hits.
- [ ] Given the same grep for `_bind_app_to_needs_application_commands`, then there are zero hits.
- [ ] Given `packages/arvel/src/arvel/console/entrypoint.py`, when I read it, then the helper functions related to the old binding logic are gone; the function names map cleanly to the new `plan_bootstrap` flow.
- [ ] Given `make pre-commit` and `make ci`, when run, then both finish with zero errors and zero warnings.

**Security Requirements**:

- [ ] None.

**Documentation Requirements**:

- [ ] None beyond what Story 7 covers.

**Requirement Refs**: NEW
**Priority**: Must
**Complexity**: Small
**Status**: Ready

**Dependencies**: Stories 1–6.

---

## Dependencies

```
Story 1 (CliSubsystem)
    └── Story 2 (provider tags)
            └── Story 3 (Command.requires)
                    └── Story 4 (bootstrap algorithm)
                            └── Story 5 (migrate built-ins)
                                    └── Story 7 (docs)
                                    └── Story 8 (benchmarks)
                                    └── Story 9 (plug-ins)
                                    └── Story 10 (cleanup)

Story 6 (openapi:export) — independent; lands in the same WI.
```

## Notes

- **Autonomous-mode assumptions** (recorded for audit):
  - Foundation subsystems are exactly `{CONFIG, LOG, LANG, CONTEXT}`. `Observability` is *not* foundation — it's opt-in. Defaults to off in dev; productions that want it set `requires` on the commands they care about (typically none — observability is for the running ASGI app, not the CLI).
  - User providers default to `USER_PROVIDERS` rather than requiring explicit annotation. Plug-in authors can override.
  - The `Command` API change (`requires` replacing `needs_application`) is a hard break with no shim, per the workspace `no-backward-compatibility` rule.
  - `openapi:export --output` drops the path-traversal guard. The CLI invoker is trusted (same model as `cp`).
  - `--output -` is added as POSIX-style sugar for `--stdout` for ergonomics; both flags coexist.
  - Cold-start thresholds in Story 8 are starting points; the bench file documents them as adjustable with a one-line PR if the CI hardware changes.

- **Out of scope (deferred to separate WIs):**
  - Migrating `cache:*` and `schedule:run` off nested `asyncio.run()`.
  - Reworking `Command.call(name, args)` to actually pass `args` through.
  - Adding new CLI commands.
  - Auto-detection of "what does this command actually call" via container introspection.

- **Cross-cutting:**
  - Stage 4 (Validation) must verify cold-start benchmarks pass on the CI runner; thresholds are part of the gate.
  - All commands under provider `commands()` methods are reviewed — Stage 4 includes a grep for `needs_application` across the whole workspace including kits.
