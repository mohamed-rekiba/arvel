# ADR-001 — Foundation & Project

**Status**: Accepted
**Date**: original decisions 2026-05-17 – 2026-05-17; merged into one ADR on 2026-06-07 during the WI-arvel-005 consolidation pass
**Scope**: Stack selection, DI container, monorepo layout, packaging strategy, app skeleton, route registration, docs site.

## Why this is one ADR

These seven decisions all answer the same question — what shape is Arvel as a project? — and constrain every later ADR. They were taken together in the first design pass and read clearer end-to-end than as seven separate files.

---

## § 1 — Adopt FastAPI + Pydantic + SQLAlchemy + Alembic + Taskiq as the framework stack

**Originally**: ADR-001 · Date: 2026-05-17

### Context

Arvel is a Laravel-style web framework for Python. The first architectural choice — and the one that constrains every other decision — is what underlying libraries to integrate with versus replace. Existing Python frameworks vary: Django and Masonite rebuilt their own ORM/router/container; Uvicore kept FastAPI but rebuilt the ORM on SQLAlchemy Core; the lighter FastAPI scaffolders layered conventions without replacing core libs.

We commit one way before writing framework code.

### Options considered

#### Option A — Build our own ORM/router/validation (Masonite path)

**Pros**: total control, Laravel-faithful naming. **Cons**: decades of work to reach SQLAlchemy/FastAPI/Pydantic parity; we'd be the sole maintainer of a major ORM in 2026; non-standard, untyped, community distrust.

#### Option B — Integrate the standard async stack (chosen)

**Pros**: ride the strongest async-Python ecosystem; inherit type-safety from Pydantic and SQLAlchemy (`Mapped[T]`, `BaseModel`); free OpenAPI from FastAPI; free async DB + migrations from SQLAlchemy + Alembic; free async queue from Taskiq; contributors already know these libraries. **Cons**: tied to the major-version cadence of several libraries (SemVer discipline mitigates); some Laravel UX needs wrappers (`where("name","x")` → `where(Model.name == "x")`).

#### Option C — Adopt Litestar instead of FastAPI

**Pros**: built-in DI, higher synthetic throughput. **Cons**: smaller ecosystem, less OpenAPI tooling, and an audience mismatch — Arvel's audience overlaps heavily with FastAPI's.

### Decision

**Option B.** Arvel is the conventions-and-DX layer on top of the standard async-Python stack. The current locked stack (minimum floors from `packages/arvel/pyproject.toml`):

| Concern | Library |
|---|---|
| HTTP / ASGI | FastAPI 0.136+ / Starlette 1.0+ / Uvicorn 0.47+ |
| Validation / DTOs | Pydantic 2.13+ |
| Settings | pydantic-settings 2.14+ |
| ORM | SQLAlchemy 2.0+ (`Mapped`, `mapped_column`, asyncio) |
| Migrations | Alembic 1.18+ + custom Schema DSL wrapping it |
| Queue | Taskiq 0.12+ (Redis/AMQP brokers via optional extras) |
| Cache | redis-py 7.4+ (optional extra) |
| Templates | Jinja2 3.1+ |
| Serialization | msgspec 0.21+ |
| Observability | OpenTelemetry SDK + structlog 25.5+ |
| Crypto | cryptography 48+ |
| Hashing | argon2-cffi (default, core dep); bcrypt 5.0+ (opt-in extra) |
| CLI | Typer 0.25+ |
| Tests | pytest + pytest-asyncio + httpx |

### Consequences

- Arvel's identity is "conventions and DX over the standard stack", not "a from-scratch framework".
- Later ADRs take this stack as given.
- The performance budget is set against the *raw* libraries (≤ 5% overhead target).
- Positioning: "If you've used FastAPI and Pydantic, you already know most of Arvel."

### Current implementation

- Dependencies: `packages/arvel/pyproject.toml` (`[project] dependencies`, `[project.optional-dependencies]`).
- Architecture overview: `docs/architecture/overview.md`.

### Notes

- Hashing reconciled: `argon2-cffi` is a core dependency and the default; `bcrypt` is an opt-in extra. See ADR-010 § 1, which is being reconciled to match this layout.

---

## § 2 — Build a custom DI container instead of adopting Dishka/Lagom/Punq

**Originally**: ADR-002 · Date: 2026-05-17

### Context

Laravel's service container is a defining feature: autowiring from type hints; singleton/scoped/transient lifetimes; contextual binding; tagged bindings; extending (decorating) resolved services; and request/worker-aware scoped resolution. Python has three mature DI containers — Dishka (FastAPI-integrated, scope/component model), Lagom (type-based, mypy-friendly), and Punq (simple type wiring). None covers contextual binding + tagging + extending in one container.

### Options considered

#### Option A — Use Dishka

**Pros**: endorsed by FastAPI, community-vetted, sophisticated scopes. **Cons**: its providers/scopes/components mental model differs from Laravel's container/providers/facades; users would learn both; no first-class contextual binding or Laravel-style tagging; API evolution tied to Dishka's roadmap.

#### Option B — Use Lagom

**Pros**: smallest footprint, type-based. **Cons**: no contextual binding or tagging — we'd hand-roll most of Laravel's surface anyway.

#### Option C — Build our own (chosen)

**Pros**: 100% mappable to Laravel's container surface; owned at the type-checker level so `make[T] -> T` holds under both strict checkers; evolution decoupled from any third party; small, well-bounded module; gives a clean `dep(T)` bridge into FastAPI's `Depends` without dragging in another runtime. **Cons**: we own the resolution algorithm, scopes, and contextual matching.

### Decision

**Option C.** `arvel.container.Container` provides bind/singleton/instance/scoped bindings, autowiring from `__init__` type hints, contextual bindings, tagging, async factories, and scope management. `dep(T)` bridges container resolution into FastAPI dependencies.

### Consequences

- The container is critical infrastructure and carries a high coverage floor (see ADR-002 § 4).
- Its behavior is a public contract, documented in the architecture docs.
- Generic-heavy resolution is designed types-first so both strict checkers infer `make[T] -> T`.

### Current implementation

- Code: `packages/arvel/src/arvel/container/`, `packages/arvel/src/arvel/dep.py`.
- Docs: `docs/architecture/service-container.md`.

### Notes

- The previously-mooted optional "Dishka-compatible adapter" was **not** shipped. The container is non-magical, so raw FastAPI `Depends` remains available for users who prefer it; that is not the blessed path.

---

## § 3 — Monorepo with `uv` workspaces

**Originally**: ADR-003 · Date: 2026-05-17 · Status: Accepted (skeleton-distribution mechanism superseded — see Notes)

### Context

Two repository shapes were available: polyrepo (Laravel's PHP/Composer approach — each thing in its own repo, auto-split from an internal monorepo) versus a monorepo with workspace tooling (one repo, multiple packages, one lockfile, atomic cross-package changes). In Python 2026 `uv` has first-class workspace support, which 2013-era PHP lacked.

### Options considered

#### Option A — Polyrepo like Laravel

**Pros**: smaller per-repo surface, fork-friendly per package. **Cons**: cross-cutting features need coordinated PRs; CI duplicated; fragmented issues; painful refactors during 0.x rapid iteration.

#### Option B — Pure monorepo

**Pros**: atomic cross-package PRs, one CI, one lockfile, one issue tracker, refactor-friendly. **Cons**: external users want "just the skeleton" without dev clutter.

#### Option C — Monorepo (+ generated skeleton) — chosen

**Pros**: monorepo DX for maintainers, clean project-generation UX for users. **Cons**: one extra generation/packaging step.

### Decision

**Monorepo with `uv` workspaces.** `tool.uv.workspace.members = ["packages/*", "kits/*"]`. One `uv.lock` at the repo root; shared dev tooling (ruff, mypy, pyright, pytest, pre-commit) configured at root. Per-package `pyproject.toml` declares each package's own dependencies; cross-package dev refs use `tool.uv.sources.<pkg> = { workspace = true }`. Companion libraries live under `packages/`; starter kits (reference apps scaffolded by `arvel new --kit`) live under `kits/`.

Current workspace members:

| Member | Location | Role |
|---|---|---|
| `arvel` | `packages/` | The framework (ships the `arvel` CLI binary) |
| `arvel-audit` | `packages/` | Audit-log companion |
| `arvel-image` | `packages/` | Image manipulation companion |
| `arvel-oauth` | `packages/` | OAuth/social-login companion |
| `arvel-permission` | `packages/` | Roles & permissions companion |
| `arvel-search` | `packages/` | Full-text / engine-backed search companion |
| `arvel-ecommerce-kit` | `kits/` | Reference application + `--kit ecommerce` source (not published) |

### Consequences

- CI runs across workspace members; `uv` handles caching natively.
- During 0.x the framework and companions iterate together; post-1.0 they can diverge on cadence.
- New first-party companions start as their own `packages/*` member when surface or release cadence justifies it.

### Current implementation

- Layout: `packages/*` (companion libraries), `kits/*` (starter kits), root `pyproject.toml` (`[tool.uv]`), `uv.lock`.
- Docs: `docs/contributing/repo-and-build.md`, `docs/packages/overview.md`.

### Notes

- **Superseded mechanism**: the original ADR specified a separate `arvel-cli` workspace member and an external `skeleton/` repo auto-split via `git subtree`. Neither exists today. The CLI was consolidated into the single `arvel` binary (ADR-017 § 6, ADR-017 § 6), and the project skeleton is packaged inside `arvel` (`packages/arvel/src/arvel/_skeleton/`) and rendered by `arvel new`. The monorepo + `uv` workspace decision itself still holds.

---

## § 4 — Single `arvel` package with optional extras; companions as separate distributions

**Originally**: ADR-004 · Date: 2026-05-17 · Status: Accepted (revised — see Notes)

### Context

Laravel ships ~30 first-party packages, each installable independently, held together by Composer's metadata graph. Python's equivalent question: ship `arvel-container`, `arvel-orm`, `arvel-queue`, … or one `arvel` with optional extras?

### Options considered

#### Option A — One package per subsystem (Laravel pattern)

**Pros**: install only what you use. **Cons**: 30+ lock-step releases; awkward cross-package imports in Python; harder type stubs and circular-dep avoidance; poor discoverability; multiplies coordination cost at 0.x.

#### Option B — Single `arvel` package with optional extras (chosen for core)

**Pros**: `pip install arvel[redis,postgres,queue]` mirrors Laravel UX; core code lives together under one import path and one `__all__`; one release artifact, CHANGELOG, and upgrade guide; refactor-friendly. **Cons**: all optional-import paths land in site-packages (small disk cost, no runtime cost — driver modules lazy-import); requires discipline on extras boundaries (enforced by import-error tests).

#### Option C — Hybrid: split major subsystems when real demand emerges

Considered for post-1.0; partially realized already via the companion packages below.

### Decision

The **core framework ships as a single `arvel` package** with optional extras for drivers. **Self-contained companions ship as their own PyPI distributions** and are surfaced as extras on `arvel`. There is no separate `arvel-cli` package — the CLI binary ships inside `arvel`.

Driver/integration extras on `arvel` (from `packages/arvel/pyproject.toml`):

`bcrypt`, `redis`, `postgres`, `mysql`, `sqlite`, `queue`, `queue-redis`, `queue-amqp`, `mail`, `s3`, `gcs`, `azure`, `jwt`, `broadcasting`, `shell`, `openapi`, `dev`.

Companion-package extras (each pulls a separate distribution):

`permission` → `arvel-permission`, `image` → `arvel-image`, `image-heif` → `arvel-image[heif]`, `oauth` → `arvel-oauth`, `search` → `arvel-search`, `audit` → `arvel-audit`.

`arvel[all]` aggregates everything.

### Consequences

- Driver modules lazy-import with a clear `ImportError` pointing at the extra to install (e.g. "install `arvel[redis]`").
- Each extra has a driver-availability test; CI installs all extras.
- Companions depend on `arvel` but version and release on their own track.

### Current implementation

- Extras: `packages/arvel/pyproject.toml` (`[project.optional-dependencies]`).
- Companions: `packages/arvel-*`; docs at `docs/packages/overview.md`.

### Notes

- **Revised from the original**: the original ADR specified exactly two packages (`arvel` + `arvel-cli`). The CLI was folded into the `arvel` binary (ADR-017 § 6, ADR-017 § 6), and several subsystems graduated to standalone companion distributions (`arvel-audit`, `arvel-image`, `arvel-oauth`, `arvel-permission`, `arvel-search`). The core principle — single core package, drivers as extras — holds.
- The original `mail-ses` / `mail-resend` / `auth-jwt` / `auth-oauth` / `storage-*` extra names were consolidated into the current set above.

---

## § 5 — Canonical application layout

**Originally**: ADR-005 · Date: 2026-05-17 · Status: Accepted (amended 2026-05-17 — lowercase all directories)

### Context

Arvel's contract with users is "Laravel for Python", which needs one canonical project shape. Without a `bootstrap/`, `routes/`, or `config/` convention, users would invent their own layouts and "Laravel-like" would be a marketing claim rather than a verifiable structure. The CLI also needs a canonical tree to scaffold from.

Three options were considered: mirror Laravel 1-for-1 (familiar, but PHP-isms like `App\Http\Kernel` don't translate); a Pythonic lowercase layout (idiomatic, PEP 8, familiar enough); or a custom Arvel-native layout (defeats the positioning).

### Decision

**Pythonic lowercase layout**, ratified into the constitution as Article X. The structure scaffolded for every generated Arvel project (mirrors the packaged skeleton):

```
my-app/
├── bootstrap/
│   ├── app.py              # create_application() — the only composition root
│   └── providers.py        # top-level providers = [...] list
├── public/
│   └── asgi.py             # asgi = create_application().into_asgi()
├── routes/
│   ├── api.py
│   ├── console.py
│   └── web.py
├── config/
│   ├── app.py
│   ├── database.py
│   ├── logging.py
│   └── view.py
├── app/
│   ├── http/
│   │   ├── controllers/
│   │   ├── middleware/
│   │   ├── requests/
│   │   └── resources/
│   ├── models/
│   ├── providers/
│   └── console/
│       └── commands/
├── database/
│   ├── migrations/
│   ├── factories/
│   └── seeders/
├── storage/
├── tests/
│   ├── feature/
│   └── unit/
├── .env.example
├── .gitignore
├── README.md
├── pyproject.toml
└── uv.lock
```

Conventions:
- **All directories**: lowercase (PEP 8). No PascalCase directory names.
- **Filenames**: snake_case (`user_controller.py`).
- **IDs**: UUID v7 everywhere — time-sortable, no sequential enumeration.
- **Composition root**: `bootstrap/app.py::create_application()` is the only function that constructs an `ApplicationBuilder`.

Changes to this layout are **breaking** per Article X §7 and require a major version bump after 1.0.

### Consequences

**Positive**:
- Fully PEP 8 compliant; `from app.http.controllers.user_controller import UserController` is idiomatic.
- No special-casing in linters or import checkers.
- New users get one obvious shape, copied verbatim from the scaffolder.

**Negative**:
- Projects started before the lowercase amendment show renames.

### Current implementation

- Authoritative skeleton: `packages/arvel/src/arvel/_skeleton/` (rendered by `arvel new`).
- Loader contract: ADR-001 § 6.
- Docs: `docs/architecture/bootstrap-lifecycle.md`, `docs/console/cli-architecture.md`.

### Notes

- **Reconciled**: enforcement is no longer "the skeleton in `arvel-cli`". The skeleton is packaged inside `arvel` at `_skeleton/` and rendered by the `arvel new` command (ADR-017 § 6, ADR-017 § 6). A smoke test verifies `arvel new` produces the expected tree.

---

## § 6 — `with_routing(...)` loader design

**Originally**: ADR-006 · Date: 2026-05-17

### Context

The canonical layout (ADR-001 § 5) puts route declarations in
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

### Decision

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

### Consequences

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

### Current implementation

- Code: `packages/arvel/src/arvel/application/application.py`
  (`with_routing`, the boot-time loader) and the path-loader helper it calls.
- Docs: `docs/architecture/bootstrap-lifecycle.md`, `docs/http/routing.md`.

### Notes

- **Reconciled**: `with_routing()` accepts `web=`, `api=`, and `console=`, but
  only **`web` and `api` are loaded at boot today**. The `console` path is
  validated and stored on the application (`_routing_paths["console"]`) but the
  loader skips it — console commands are discovered via entry points and
  `ConsoleServiceProvider` instead (see `docs/console/cli-architecture.md`).
  Loading `routes/console.py` is deferred work, not a shipped behavior.

---

## § 7 — Adopt mkdocs-material now; auto-generate API reference from docstrings

**Originally**: ADR-007 · Date: 2026-05-17

### Context

Foundations shipped without a published docs site (FB-004). The constitution (Article V) lists `mkdocs build --strict` as a CI gate that was deferred to post-Phase-11. The HTTP layer adds ~30 public symbols on top of the foundations' 18; a published reference becomes valuable now, not later.

### Decision

Bootstrap a `mkdocs-material` site from WI-002. Two pillars:

1. **Hand-written narrative docs** under `docs/site/` — install, quickstart, container, providers, config, routing, controllers, form-requests, resources, middleware, auth, throttle, csrf, exceptions. One page per concept.
2. **Auto-generated API reference** via `mkdocstrings` (Python handler) — renders type signatures + docstrings for every public symbol under `arvel.*`. No hand-maintained reference table.

`mkdocs.yml` lives at repo root. `mkdocs build --strict` is a CI gate from this WI onwards.

### Why now (override the deferral)

- Public surface is non-trivial after WI-002. The longer we wait, the more docstring debt.
- `mkdocstrings` paired with our strict typing means the reference is always in sync — adding the gate now prevents drift.
- The constitution already lists this gate; we're moving the activation date in, not adding a new gate.
- FB-004 was scoped as "low priority" only because foundations had a small surface; the cost-benefit flips at HTTP scale.

### Why mkdocs-material

- Best-in-class search out of the box.
- First-class `mkdocstrings` integration.
- Themable to match Laravel-style docs visually.
- Mature, single-vendor (Squidfunk), strong release cadence.

Alternatives considered:
- **Sphinx**: more powerful but heavier; reStructuredText hostile to drive-by contributors.
- **Docusaurus**: forces a Node toolchain into a Python-only repo.

### Trade-offs

- One more CI gate to fail on (`mkdocs build --strict`).
- Docstring discipline becomes mandatory (was already constitution Article IX.1 — this enforces it).
- A new dev-time tool (`uv add --group docs mkdocs-material mkdocstrings[python]`).

### Consequences

- Adds `docs` dependency group in `pyproject.toml` (root + arvel package).
- New `make docs-serve` and `make docs-build` targets.
- New CI job `docs` (parallel with lint/typecheck/test).
- Hosting: GitHub Pages from the `gh-pages` branch (set up post-publish, not gating this WI).

---

### Cross-references

- PRD-002: FR-002-028, NFR-002-006
- Constitution Article V (`mkdocs build --strict` gate)
- Backlog item: FB-004

---

## Subsumes

This ADR absorbs the following ADRs in the WI-arvel-005 consolidation pass (2026-06-07). The original files are deleted; their decision text is preserved verbatim above in the corresponding `§` sections.

| Old | Date | Subject | New location |
|---|---|---|---|
| ADR-001 | 2026-05-17 | Adopt FastAPI + Pydantic + SQLAlchemy + Alembic + Taskiq as the framework stack | § 1 |
| ADR-002 | 2026-05-17 | Build a custom DI container instead of adopting Dishka/Lagom/Punq | § 2 |
| ADR-003 | 2026-05-17 | Monorepo with `uv` workspaces | § 3 |
| ADR-004 | 2026-05-17 | Single `arvel` package with optional extras; companions as separate distributions | § 4 |
| ADR-005 | 2026-05-17 | Canonical application layout | § 5 |
| ADR-006 | 2026-05-17 | `with_routing(...)` loader design | § 6 |
| ADR-007 | 2026-05-17 | Adopt mkdocs-material now; auto-generate API reference from docstrings | § 7 |
