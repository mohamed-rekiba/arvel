# ADR-024 — Typer Single-Command Promotion Workaround

**Status**: Accepted
**Date**: 2026-05-17
**Deciders**: Arvel core team

---

## Context

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

## Decision

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

## Consequences

- **Positive**: `Application` behaves identically regardless of how many commands
  are registered — one command, two, or twenty.
- **Positive**: `arvel` with no arguments prints a help screen, matching the
  Laravel Artisan UX.
- **Negative**: A tiny extra callback is always registered. No measurable overhead.
- **Watch out**: If Typer changes this behaviour in a future version, the `_noop`
  becomes a no-op wrapper of a no-op — harmless but can be removed.
