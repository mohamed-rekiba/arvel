# Epic: Async CLI commands must honor the single-event-loop contract

## Summary
The CLI entrypoint owns one event loop (`asyncio.run(async_main())`) and dispatches
Typer synchronously on it, then awaits whatever a command defers via
`schedule_async()`. Nine command callbacks instead called `asyncio.run(...)` directly,
which nests on the live loop and crashes in-project with "asyncio.run() cannot be
called from a running event loop". They passed `CliRunner` unit tests (no outer loop)
but broke the moment they ran in a real project. Coupled defect: the entrypoint didn't
translate a `typer.Exit`/`Abort` raised inside the deferred coroutine into a process
exit code, so an honest failure escaped as a traceback. All 9 commands now defer via
`schedule_async`; the entrypoint maps a deferred Exit/Abort to the exit code; and the
cache-backed commands declare `requires={CACHE}`.

**Module:** console · **Spec:** `docs/pipeline/specs/WI-arvel-014-cli-single-event-loop.md`

## Stories

### Story 1: Async commands run in a real project
**As a** developer running `arvel` in my project, **I want** async commands to run on
the framework's event loop, **so that** they don't crash with "asyncio.run() cannot be
called from a running event loop".

**Acceptance Criteria**:
- [x] Given any of the 9 async commands (`cache:clear`, `cache:forget`, `schedule:run`, `db:show`, `db:table`, `queue:clear`, `queue:prune-failed`, `queue:restart`, `auth:clear-resets`), when its callback runs, then it defers via `schedule_async` and never calls `asyncio.run`.
- [x] Given a deferred coroutine raises `typer.Exit(code)`, when the entrypoint awaits it, then the process exits with `code` (no traceback).
- [x] Given a deferred coroutine returns normally, when the entrypoint awaits it, then the process exits 0.

**Security Requirements**:
- [x] None (loop-ownership / exit-code plumbing only).

**Documentation Requirements**:
- [x] `docs/site/docs/cli/commands.md` notes the single-event-loop contract for command authors (defer async work; don't call `asyncio.run` in a callback).

**Requirement Refs**: SPEC-1, SPEC-4, SPEC-5
**Priority**: Must · **Complexity**: Small · **Status**: Done

### Story 2: Cache-backed commands boot the cache provider
**As an** operator, **I want** `cache:clear`, `cache:forget`, and `queue:restart` to
boot the cache subsystem, **so that** they act on the real cache instead of an unbound
one.

**Acceptance Criteria**:
- [x] Given `cache:clear` / `cache:forget`, then `CliSubsystem.CACHE` is in `requires`.
- [x] Given `queue:restart` (writes its restart marker via the cache), then `CliSubsystem.CACHE` is in `requires`.

**Requirement Refs**: SPEC-2, SPEC-3
**Priority**: Must · **Complexity**: Small · **Status**: Done

## Dependencies
- Builds on WI-031 (single-event-loop contract for `migrate`/`db:seed`). Independent of
  WI-arvel-001..013.

## Notes
- `serve`/`shell` keep `owns_process=True` and run outside the `asyncio.run` wrapper —
  unchanged.
- Folded-in: fixed a Python-2 `except A, B:` `SyntaxError` in
  `tests/console/conftest.py` that made the console suite uncollectable from HEAD;
  switched the cache/introspection/queue tests that assert deferred behavior to the
  `invoke_async` helper.
- Deferred follow-ups (separate work items):
  - **`Application.run()` → `handle()` bypass** — register-style commands raise
    `NotImplementedError` via `Command.call()` / the scheduler `run_command` hook.
  - **Stale doc pointer** — `make_command.py` references a non-existent `artisan.md`.
