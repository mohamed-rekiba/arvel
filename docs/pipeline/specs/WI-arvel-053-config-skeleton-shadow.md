# WI-arvel-053 — Remove workspace-root `config/` skeleton shadow

- **Complexity**: L1
- **Risk tier**: 1
- **Data classification**: internal
- **Status**: completed
- **Origin**: deferred finding F7 (monorepo test-harness import collision)

## Problem

The observability config skeleton shipped as `config/observability.py` at the
**workspace root**, alongside a `config/__init__.py` — a real, importable
top-level `config` package.

pytest's default (prepend) import mode and the kit's own `conftest.py` both put
their roots on `sys.path`. When the workspace root lands ahead of a consumer's
backend root, a bare `import config` resolves to the workspace skeleton instead
of the consumer's `config/` package. The skeleton has no `app`/`auth`/… modules,
so the consumer's `import config.app` (and friends) raise
`ModuleNotFoundError: No module named 'config.app'`.

Reproduced deterministically:

```python
sys.path.insert(0, "<kit>/backend")
sys.path.insert(0, "<workspace-root>")  # prepend mode puts rootdir first
import config        # -> workspace-root config/__init__.py  (the skeleton)
import config.app    # -> ModuleNotFoundError
```

This is exactly F7: behind a workspace-root run, kit unit tests that import
`config.*` / `app.*` at runtime break. (The kit suite passes when run in
isolation because the kit conftest wins the `sys.path[0]` race — the breakage
only surfaces once the root `config` package is on the path.)

## Fix

Root cause is the *location* of the skeleton, not the import machinery:

1. Moved the skeleton to the app scaffold:
   `packages/arvel/src/arvel/_skeleton/config/observability.py`, next to its
   siblings (`app.py`, `database.py`, `logging.py`, `view.py`). It's scaffolded
   into new apps from there.
2. Deleted the workspace-root `config/` package
   (`config/__init__.py`, `config/observability.py`). The repo root no longer
   exposes a top-level `config` package, so nothing can shadow a consumer's.
3. Repointed `test_wi_030_config.py::test_config_skeleton_file_exists` to assert
   the skeleton at its canonical scaffold path
   (`arvel.__file__` → `_skeleton/config/observability.py`), resolved relative to
   the package rather than the test CWD.

Arvel's own config loader was never affected: `with_config_dir` loads config
files under a namespaced module prefix (`_arvel_user_app.config.*`) specifically
so user config never shadows stdlib or sibling packages.

## Tests / gates

- `test_wi_030_config.py` — 11 passed (skeleton-exists check now hits the scaffold path)
- All five `_skeleton/config/*.py` load cleanly through the config loader
- Kit unit suite from the workspace root — 350 passed
- Application + scaffold suites — 263 passed
- Manual `sys.path` repro now resolves `import config` → kit's `config`, `config.app` OK
- ruff + mypy clean on touched files
