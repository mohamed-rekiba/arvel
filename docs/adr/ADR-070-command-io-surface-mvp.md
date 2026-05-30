# ADR-070 — `Command` / `Context` I/O surface: ship the minimum-viable subset, defer prompts and tables

**Status**: Accepted
**Date**: 2026-05-19
**Supersedes**: none
**Superseded by**: none
**Related**: ADR-068 (CLI framework bootstrap), PRD-021 FR-021-23, FR-021-24

## Context

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

### Options

**Option 1 — Ship nothing new.** Defer the entire `Context` surface to FB-022. Pro: smallest WI-021 diff. Con: WI-021 implements many commands that legitimately need `warn` (e.g., `migrate:status` warns about pending migrations) and `alert` (e.g., `key:generate` alerts on `--force` overwrite). They'd all use `ctx.error()` (red text on stderr) inappropriately, polluting the semantics for actual errors.

**Option 2 — Ship the full Laravel surface.** Implement everything: prompts, tables, progress bars, signal trap, isolation, etc. Pro: parity with one stroke. Con: doubles the WI-021 scope; prompts in particular need careful TTY-vs-non-TTY behaviour (auto-answer in CI), test infrastructure, and a non-trivial dependency on `prompt-toolkit` or `questionary` for a good UX.

**Option 3 — Ship the non-interactive writes + cross-command call.** Add `warn`, `comment`, `alert`, `newline` to `Context`. Add `Command.call(name, args)` and `Command.call_silently(name, args)` (uses the existing `Application.run()` from WI-020). Skip everything that requires user input or terminal capabilities (prompts, tables, progress bars, trap, isolation). Pro: serves every command shipped in WI-021 without compromising semantics; testable without TTY mocking; small diff (~30 LoC + tests). Con: still leaves a parity gap users will notice.

## Decision

**Option 3 — minimum-viable: ship the non-interactive write surface + cross-command call. Defer prompts, tables, progress bars, signal trap, and isolation to FB-022-003/004/005.**

### Concrete API surface

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

## Out of scope (deferred — captured for FB-022)

| Feature | Reason for deferral | Tracking |
|---|---|---|
| `ask`, `confirm`, `choice`, `secret`, `anticipate` | Needs careful TTY-vs-non-TTY behaviour, auto-answer in CI, and a prompt library dependency decision (`prompt_toolkit` vs `questionary` vs roll-your-own) | FB-022-003 |
| `table(headers, rows)` | Wants column-width calculation, alignment, multi-line cell support — substantial implementation; out of WI-021 scope | FB-022-003 |
| `progress(total)` | Same as table; also overlaps with `rich.progress` if we depend on `rich` | FB-022-003 |
| Signal `trap(SIGTERM, ...)` | Useful for queue workers and scheduler — but those work today via `loop.add_signal_handler` directly; the convenience wrapper is nice-to-have | FB-022-004 |
| `implements Isolatable` + mutex | Cross-cutting concern that needs a lock backend decision (file? Redis? DB?). Best delivered together with the lock backend, not bolted onto a single WI | FB-022-005 |
| `PromptsForMissingInput` trait | Depends on the prompt surface (FB-022-003) | FB-022-003 |
| `argument(name)` / `option(name)` retrieval helpers | Typer callback params already provide typed access; helpers would only help when commands implement `handle()` AND want positional/keyword args. Of the WI-021 commands, none need this — `register()`-pattern commands use Typer params directly | FB-022-006 |

## Consequences

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

## Implementation notes

- ANSI colour escapes are unconditional today. A follow-up could add `NO_COLOR` env var support (standard convention, FB-022-007).
- `Context.alert()`'s box-drawing falls back to `***` when stdout isn't a TTY because Unicode box characters render poorly in CI log viewers (GitHub Actions, GitLab CI).
- Tests use `capsys` to assert escape codes are present in TTY mode and absent in non-TTY (monkeypatch `sys.stdout.isatty` to return False).
- `Command.call_silently()`'s suppression is best-effort: if the invoked command writes directly to `sys.stderr` via `os.write(2, ...)` or similar, that bypass is not caught. Documented as "captures Python-level writes; subprocess output is the caller's responsibility."
