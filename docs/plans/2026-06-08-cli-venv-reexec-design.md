# Global `arvel` CLI → project `.venv` re-exec

**Date:** 2026-06-08
**Status:** Implemented

## Problem

The `arvel` console script runs on whatever interpreter it was installed into. A globally-installed `arvel` (pipx, `uv tool install`, system pip) runs on the global interpreter, whose `sys.path` points at global site-packages — not the project's `.venv`. When it imports the user's `bootstrap/app.py`, the import chain resolves the wrong arvel version and misses the project's extras (asyncpg, argon2/cryptography wheels are ABI-specific per interpreter). The user has to `source .venv/bin/activate` first.

## Goal

Type `arvel <cmd>` from anywhere inside a project, without activating the venv, and have it run with the project-pinned arvel + the project's deps.

## Chosen approach: re-exec shim

The global `arvel` becomes a thin launcher. The first thing `main()` does is detect the project's `.venv` and, if it's not already running on it, hand off via `os.execve` to the venv's own `arvel` (or `python -m arvel`). The replaced process then runs exactly as if the venv were activated.

`os.execve` replaces the process image rather than spawning a child, so exit codes, stdio, and Ctrl+C pass through with no plumbing.

### Alternatives considered

- **Inject the venv's site-packages into `sys.path`** — rejected. Mixing site-packages across interpreters with different Python versions / ABIs is unsafe (compiled wheels break).
- **Detect + print an "activate" message** — simpler, but doesn't run the command; keeps friction. The user chose pure re-exec over this and over a hybrid.
- **Status quo (`uv run arvel` / manual activate)** — works today; the goal was the zero-friction global UX.

## Detection precedence

1. `ARVEL_NO_REEXEC=1` (opt-out) or `ARVEL_VENV_REEXEC=1` (internal loop guard) → skip.
2. `find_project_root()` returns `None` (outside a project) → skip.
3. No `<root>/.venv/bin/python` (POSIX) / `.venv\Scripts\python.exe` (Windows) → skip, run as-is.
4. `Path(sys.executable).resolve()` equals the venv python → already inside → skip.
5. Otherwise re-exec: prefer `<root>/.venv/bin/arvel`; fall back to `<venv>/bin/python -m arvel` when the script is absent but the `arvel` package is importable in the venv. If neither exists, skip (let the normal flow surface its own error).

The re-exec sets `ARVEL_VENV_REEXEC=1` in the child env so the second leg never re-execs again.

## Key decisions

- **Runs before the banner** so there's no double banner (only the venv leg prints it).
- **`sys.executable` comparison, not `$VIRTUAL_ENV`** — correctly stays quiet even when someone runs `.venv/bin/arvel` directly without exporting `VIRTUAL_ENV`.
- **Windows** uses `subprocess.run` + `sys.exit(rc)` because `os.execve` there spawns a child and the parent keeps running.
- **`.venv` convention only** — the path lives in one place in `_venv.py`; adding `venv/` or an override is a one-line change later (YAGNI for now).
- **S606/S603 suppression** — `os.execve` / `subprocess.run` are flagged by ruff+bandit. The target is the project's own `.venv` path located on disk, no shell, no untrusted input. Suppressed with justified `# noqa: S606 # nosec B606` (and `S603/B603`), matching the existing convention in `new.py`.

## Files

| File | Change |
|---|---|
| `packages/arvel/src/arvel/console/_venv.py` | New — `maybe_reexec_into_project_venv` + helpers, stdlib only |
| `packages/arvel/src/arvel/__main__.py` | New — enables `python -m arvel` (fallback exec target) |
| `packages/arvel/src/arvel/console/entrypoint.py` | One call at the top of `main()` |
| `packages/arvel/tests/console/test_venv_reexec.py` | New — triggers, opt-outs, loop guard, already-inside, no-venv, outside-project, exec branch |
| `docs/site/docs/cli/commands.md` | "Global install and the project virtualenv" section |

## Non-goals

- Supporting venv dirs other than `.venv`.
- Auto-creating or syncing the venv.
- An activation-hint message (explicitly dropped in favour of pure re-exec).
