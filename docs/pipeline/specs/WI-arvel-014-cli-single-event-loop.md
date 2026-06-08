# WI-arvel-014 — Async CLI commands must honor the single-event-loop contract

| | |
|---|---|
| **Module** | console |
| **Complexity** | L2 | **Risk** | Tier 2 | **Data** | internal |
| **Autonomous** | yes | **Frontend** | no |
| **Research** | `.context/research/014-console.md` (C1 fixed; `Application.run`→`handle` bypass deferred) |
| **Review** | C1 confirmed systemic: 9 command callbacks nest `asyncio.run` on the entrypoint's live loop; entrypoint also drops a deferred coro's `typer.Exit` |

## Problem

The CLI entrypoint owns the one event loop: `main()` → `asyncio.run(async_main())`,
which dispatches Typer synchronously on that loop and then awaits whatever a command
deferred via `schedule_async()`. Nine command callbacks instead called
`asyncio.run(...)` directly:

```python
# cache_commands.py (before)
def _callback(...) -> None:
    ...
    asyncio.run(clear(store))   # nested on the entrypoint's running loop
```

In a real project this raises `RuntimeError: asyncio.run() cannot be called from a
running event loop`. The commands passed `CliRunner` unit tests (no outer loop) but
crashed the moment they ran in-project. Reproduced in the kit for `arvel cache:clear`,
`arvel cache:forget`, `arvel schedule:run`.

Coupled defect: `async_main` awaited the deferred coroutine but didn't translate a
`typer.Exit`/`Abort` raised *inside* it into a process exit code. Once the 9 commands
defer their work (including their failure `typer.Exit`), an honest non-zero exit would
escape as an uncaught `RuntimeError` (traceback + exit 1). This also affected the
existing WI-031 commands (`migrate`).

Subsystem mis-tag: `cache:clear`, `cache:forget`, and `queue:restart` use the Cache
facade but didn't declare `requires={CliSubsystem.CACHE}`, so `CacheServiceProvider`
never booted.

## Spec Items → Verification

| ID | Spec item | Test | Status |
|---|---|---|---|
| SPEC-1 | No async command callback calls `asyncio.run`; each defers via `schedule_async` (all 9). | `tests/console/test_wi_014_cli_async_loop.py::test_callback_defers_via_schedule_async_not_asyncio_run` (×9) | PASS |
| SPEC-2 | `cache:clear` / `cache:forget` require the CACHE subsystem. | `...::test_cache_commands_require_cache_subsystem` | PASS |
| SPEC-3 | `queue:restart` requires the CACHE subsystem (writes the marker via cache). | `...::test_queue_restart_requires_cache_subsystem` | PASS |
| SPEC-4 | A `typer.Exit(code)` raised inside the deferred coroutine becomes `SystemExit(code)`. | `...::test_async_main_translates_deferred_typer_exit` | PASS |
| SPEC-5 | A deferred coroutine that returns normally exits 0 (no traceback). | `...::test_async_main_exit_zero_on_deferred_success` | PASS |
| SPEC-6 (X-cut: types/lint) | mypy `--strict` + pyright clean; ruff clean; console suite (721) + full framework suite green. | `mypy` + `pyright` + `ruff` + `pytest` | PASS |

## Root-cause fix

- **9 commands** (`cache_commands.py` ×2, `schedule_run.py`, `db_show.py`,
  `db_table.py`, `queue_clear.py`, `queue_prune_failed.py`, `queue_restart.py`,
  `auth_clear_resets.py`) — replace `asyncio.run(coro)` with
  `arvel.console._async.schedule_async(coro)`, moving each command's post-processing
  and error handling (including the `typer.Exit(...)` raise) into an inner async
  function. They now run on the entrypoint's single loop like `migrate`/`db:seed`.
- **`entrypoint.async_main`** — after `await coro`, translate `typer.Exit` →
  `SystemExit(exc.exit_code)` and `typer.Abort` → `SystemExit(1)`.
- **`requires`** — add `frozenset({CliSubsystem.CACHE})` to `cache:clear`,
  `cache:forget`, `queue:restart`.

## Deliberate design decisions

- **Defer, don't spawn a loop.** Matches the WI-031 contract: one loop owned by the
  entrypoint, so the async DB engine / cache client a command touches is bound to the
  same loop the command's coroutine runs on. `serve`/`shell` keep `owns_process=True`
  and run outside the wrapper.
- **Translate Exit at the entrypoint, not per-command.** A single try/except around
  `await coro` keeps every deferred command honest without each one re-implementing
  exit-code plumbing.

## Out-of-scope cleanup (folded in)

- `tests/console/conftest.py` — line 104 had a Python-2 `except typer.Abort,
  click.exceptions.Abort:` (`SyntaxError` on import; the console suite was
  uncollectable from HEAD). Fixed to `except (typer.Abort, click.exceptions.Abort):`.
- `tests/console/test_cache_storage_commands.py`, `test_introspection.py`,
  `test_queue_ops_023.py` — switched the cases that assert deferred behavior from
  `runner.invoke` to the `invoke_async` helper (runs the scheduled coroutine and maps
  its `typer.Exit` to an exit code).

## Deferred (tracked)

- **`Application.run()` → `handle()` bypass** — `Application.run` calls
  `command.handle()` directly, so register-style commands raise `NotImplementedError`
  via `Command.call()` / the scheduler `run_command` hook. Dispatch through
  `typer_app(argv, standalone_mode=False)` instead. Separate WI.
- **Stale doc pointer** — `make_command.py` references `docs/site/docs/artisan.md`;
  the CLI reference is `docs/site/docs/cli/commands.md`.
