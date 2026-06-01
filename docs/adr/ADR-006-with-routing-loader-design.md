# ADR-006 — `with_routing(...)` loader design

**Status**: Accepted
**Date**: 2026-05-17
**Last reconciled**: 2026-06-01

## Context

The canonical layout (ADR-005) puts route declarations in
`routes/web.py`, `routes/api.py`, and `routes/console.py`. The composition
root in `bootstrap/app.py::create_application()` declares these paths to the
`ApplicationBuilder`:

```python
.with_routing(
    web=base / "routes" / "web.py",
    api=base / "routes" / "api.py",
    console=base / "routes" / "console.py",
)
```

The builder needs to turn those `Path` objects into imported Python modules
so that the route-decorator side effects (`@route.get("/", ...)`, etc.) fire.
Three load strategies were considered:

| Option | How it works | Pros | Cons |
|---|---|---|---|
| A. Insert `routes/` parent on `sys.path`, then `importlib.import_module("web")` | Drop the right directory on `sys.path`, then bare-name import | One-liner | Pollutes `sys.path` globally; bare module name `web` collides with anything else named `web`; survives across multiple Arvel apps in the same process |
| B. **`importlib.util.spec_from_file_location` with a namespaced module name** | Build a `ModuleSpec` directly from the file path, give it a namespaced name like `_arvel_user_app.routes.web` | No `sys.path` mutation; collision-proof namespace; explicit ownership | Slightly more code; users `inspect.getmodule()` see the namespaced name |
| C. Read the file and `exec()` it manually | Full control | Loses `__name__`, breaks relative imports inside route files, no introspection support | — |

## Decision

**Option B** — `importlib.util.spec_from_file_location` with the namespace
prefix `_arvel_user_app.<subpkg>.<stem>`.

Concrete implementation:

```python
import sys
import importlib.util
from pathlib import Path
from types import ModuleType

_NAMESPACE_PREFIX = "_arvel_user_app"

def load_module_from_path(path: Path, module_name: str) -> ModuleType:
    sys_path_before = list(sys.path)

    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ConfigurationError(f"Cannot create module spec for {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    finally:
        assert sys.path == sys_path_before, (
            "Arvel loader invariant violated: sys.path was mutated during module load"
        )

    return module
```

Module name conventions used by the three callers:

| Caller | Module name pattern | Example |
|---|---|---|
| `with_providers(Path)` | `_arvel_user_app.bootstrap.providers` | (fixed, only one file) |
| `with_routing(web=p)` | `_arvel_user_app.routes.<stem>` | `_arvel_user_app.routes.web` |
| `with_config_dir(p)` | `_arvel_user_app.config.<stem>` | `_arvel_user_app.config.database` |

The namespace prefix has a leading underscore on purpose: it signals
"framework-private namespace, do not import from user code".

The `assert sys.path == sys_path_before` is a load-time invariant, not a
test-only check. If anything underneath us (a route file, a config file, a
provider module) appends to `sys.path` mid-load, we want to fail loudly
rather than silently inherit the leak.

## Consequences

**Positive**:
- Two Arvel apps can coexist in the same Python process without their
  `config/database.py` files colliding — each gets a distinct module entry
  under `_arvel_user_app.<…>` because the apps build distinct
  `ApplicationBuilder` instances with distinct path bases. (Edge case
  mitigation: the spec key is the dotted module name; if two apps both
  contain `routes/web.py`, they'd write to the same `sys.modules` key. The
  builder appends a stable hash of the application's `base_path` to the
  namespace prefix when it detects this — implementation detail; documented
  in the executor's docstring, tested at QA-Post.)
- User's `config/logging.py` does NOT shadow stdlib `logging` because it
  lands under `_arvel_user_app.config.logging`, not bare `logging`.
- `sys.path` invariant is enforced at load time AND by a dedicated unit test
  (Gate #28).
- `inspect.getfile(module)` returns the real path, so debuggers and IDEs
  follow the user back to their own source.

**Negative**:
- Module names under `_arvel_user_app.*` show up in tracebacks. Acceptable —
  the prefix immediately signals "this is application-loaded code, not
  framework code", which is actually useful debugging context.
- Relative imports inside route/config files (`from .helpers import foo`) do
  not work because the loaded modules have no package parent. Documented in
  the skeleton README; route files in the skeleton avoid relative imports.

**Enforcement**:
- Dedicated unit test for the `sys.path` invariant.
- Integration test verifies `routes/web.py` registers `GET /` returning 200.
- Module-shadow test: a `config/logging.py` defining `LEVEL = "DEBUG"` MUST
  be loadable AND must NOT replace stdlib `logging` in `sys.modules`.

## Current implementation

- Code: `packages/arvel/src/arvel/application/application.py`
  (`with_routing`, the boot-time loader) and the path-loader helper it calls.
- Docs: `docs-fresh/architecture/bootstrap-lifecycle.md`, `docs-fresh/http/routing.md`.

## Notes

- **Reconciled**: `with_routing()` accepts `web=`, `api=`, and `console=`, but
  only **`web` and `api` are loaded at boot today**. The `console` path is
  validated and stored on the application (`_routing_paths["console"]`) but the
  loader skips it — console commands are discovered via entry points and
  `ConsoleServiceProvider` instead (see `docs-fresh/console/cli-architecture.md`).
  Loading `routes/console.py` is deferred work, not a shipped behavior.
