# CLI startup performance + banner — design

## Problem

`arvel` CLI startup is slow. Measured on the `uv tool` install (warm cache):

| What | Time |
|---|---|
| Bare interpreter (`python -c pass`) | 0.02s |
| `import arvel` (root package only) | 0.84s |
| `discover_commands()` (loads all 73 commands) | 1.18s total |
| `arvel --help` warm | ~1.0s |
| First cold run | up to 8.4s |

Root causes:

1. **`arvel/__init__.py` eagerly imports the whole framework** — FastAPI, Starlette,
   SQLAlchemy, http, validation, auth, routing — at package import time. Because the CLI
   does `from arvel.console import ...`, importing any submodule runs the root `__init__.py`
   first, so every invocation (even `--help` or `make:*` outside a project) pays ~0.84s.
2. **`discover_commands()` loads all 73 command classes on every run** (+~0.34s), even when
   only one command is requested.

## Decision: no compiled binary

Nuitka/PyOxidizer were considered for `curl | bash` install. Rejected for performance:

- Neither removes Python module-init cost. FastAPI/Pydantic/SQLAlchemy still run their
  module-level code at runtime. The 0.84s is init cost, not interpreter or import-scan cost.
- PyOxidizer saves only import-scan time (~50–150ms). Nuitka can't speed up the native
  C-extension deps (pydantic-core, sqlalchemy, cryptography) that dominate.
- Arvel is a framework: running a project needs a real Python env regardless. A binary CLI
  can't import the user's `bootstrap/app.py`. Value is limited to first-time scaffolding.

The lazy-import fix yields a 5–10x win from a code change. Install convenience is solved with
a `uv tool install` based `install.sh`, not a binary.

## Approach

### 1. Lazy framework imports (`arvel/__init__.py`) — main win
Convert eager re-exports to PEP 562 module `__getattr__`. Keep real imports under
`if TYPE_CHECKING:` so mypy/pyright/IDEs resolve types unchanged. `__version__` stays eager
(cheap string, release-please target). `ASGIApp`/`HttpLifespan` resolved lazily.
Expected: `import arvel` ~0.84s → ~0.16s (eager `config`/`dep` pull `arvel.container`, still 5x).

**Gotcha — re-exports whose name matches a submodule must stay eager.** `config`
(`arvel.config` package), `dep` (`arvel.dep` module), and `env` (`arvel.support.env`
module) are functions re-exported under the same name as a real submodule. A lazy
`__getattr__` is bypassed the moment the submodule is imported anywhere — Python sets
the submodule as the package attribute, so `from arvel import config` hands back the
module, not the function. Fix: bind these three eagerly (all import-cheap — no
FastAPI/SQLAlchemy/starlette). `arvel.dep` loads `starlette.requests.Request` via
`importlib.import_module` inside `dep()` (not at module load) so the eager bind stays
cheap; the resolver's `__annotations__` are set to the concrete class so FastAPI's
`get_type_hints` still injects the request.

### 2. Lazy command dispatch (`entrypoint.py`, `_loader.py`)
Load only the requested command's entry point on the hot path. Full discovery only for the
rare `--help`/no-arg listing (which needs every command's help text).

### 3. Always-on banner (`entrypoint.py`)
Plain ANSI banner printed first in `main()`. Printed to **stderr**, suppressed when stderr is
not a TTY, when `NO_COLOR` is set, or when `--no-banner` is passed. Safe for pipes/redirects/JSON.

### 4. Fix `--version`
Entrypoint already allow-lists `--version`/`-V` but Typer has no handler (errors today). Add a
real version callback.

### 5. `install.sh`
`curl -fsSL https://arvel.dev/install.sh | bash` → ensure `uv`, then `uv tool install arvel`.

### 6. Fast `arvel --help` (follow-up) — listing without importing commands

Even after (1)–(2), `arvel --help` outside a project was ~3.9s cold: Typer must show
every command's name + help, which meant importing all 73 command classes (27 of them pull
SQLAlchemy/FastAPI/Starlette/Jinja2/uvicorn). Two changes:

- **Option A — manifest-backed listing (outside project).** A generated, checked-in manifest
  `console/_command_meta.py` (name → short help) feeds a render-only Typer app
  (`build_listing_app()`) for the no-command / `--help` / unknown-command paths. No command
  implementation is imported. Names come from entry-point metadata; help from the manifest.
  Regenerate with `scripts/gen_command_meta.py`; a drift-guard test fails CI if it goes stale,
  and a subprocess test asserts the listing never imports the heavy stack. Real dispatch
  (`arvel <cmd>`, `arvel <cmd> --help`) still routes through `load_command` (one module), so
  the placeholders are render-only. Result: `arvel --help` ~3.9s → ~0.4s.

- **Option B — lazy in-project dispatch.** `async_main` no longer calls `discover_commands()`
  (all 73) on every invocation. For a concrete command it resolves just that one (provider
  binding wins, else `load_command`); full discovery is kept only for the in-project
  listing/unknown path. The per-invocation selection cost drops from ~2.38s (import all 73) to
  ~0.40s (light command) / ~0.86s (a command that genuinely needs SQLAlchemy). The async
  lifecycle (boot → dispatch → `get_pending_task` → shutdown) is unchanged.

## Verification
- `python -X importtime` before/after on `import arvel` and the entrypoint.
- `/usr/bin/time` on `arvel --help`, `arvel make:controller --help`, a real command.
- Existing console test suite green (`from arvel import X` must still resolve).
- `make pre-commit` / mypy / ruff clean.

## Non-goals
- No compiled binary. No new runtime deps. No change to any command's behavior.
