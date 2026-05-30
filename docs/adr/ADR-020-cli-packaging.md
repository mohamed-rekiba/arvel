# ADR-020 — `arvel-cli` packaging strategy

**Status**: Accepted
**Date**: 2026-05-17

## Context

Per constitution Article III §3, `arvel-cli` is a separate PyPI
package from `arvel`. WI-004 turns it from a stub-that-exits-2 into a real
implementation that scaffolds the canonical layout (ADR-018) into a target
directory.

Three sub-decisions need to be locked in for the implementation:

1. **Where does the skeleton live?**
2. **What CLI framework drives `arvel new`?**
3. **How are tokens like `{{ project_name }}` substituted?**

### Skeleton storage options

| Option | Pros | Cons |
|---|---|---|
| A. **Inside the wheel as packaged data** (`arvel_cli/skeleton/`) read via `importlib.resources` | One artifact to install; works offline; deterministic version match between installer and skeleton | Wheel size grows with skeleton; binary-ish content inside wheel |
| B. Separate `arvel-skeleton` package fetched at runtime | Smaller installer | Two packages to coordinate; extra network call; breaks offline use |
| C. Git clone from a known repo at install time | Always latest | Requires git; requires network; breaks corporate firewalls; version skew |

### CLI framework options

| Option | Pros | Cons |
|---|---|---|
| A. `argparse` (stdlib) | Zero deps | Verbose; awkward subcommands; no built-in completion |
| B. **Typer 0.19+** | Same stack as WI-005 console binary; type-driven; auto-completion | One dep (already in framework's transitive set) |
| C. `click` | Mature | One dep, and Typer wraps Click anyway |

### Token substitution options

| Option | Pros | Cons |
|---|---|---|
| A. **`str.replace` over a small token dict** | Zero deps; trivially reviewable; impossible to introduce template injection | No conditionals, no loops, no filters — but we don't need any |
| B. Jinja2 | Powerful | Heavy dep for the three substitutions we actually make; opens template-injection surface |
| C. `string.Template` | Stdlib | `$` syntax conflicts with shell scripts in the skeleton (`.env.example` has `${DB_HOST}` placeholders) |

## Decision

1. **Skeleton storage**: Option A — packaged data inside the wheel under
   `arvel_cli/skeleton/`, read via `importlib.resources` (`Traversable`
   API).
2. **CLI framework**: Option B — Typer 0.19+.
3. **Token substitution**: Option A — literal `str.replace` with a fixed
   token dict.

### Skeleton storage details

The skeleton tree mirrors the on-disk layout exactly, but file extensions
get a `.tmpl` suffix where templating applies:

```
arvel_cli/skeleton/
├── bootstrap/
│   ├── __init__.py
│   ├── app.py
│   └── providers.py
├── public/
│   ├── __init__.py
│   └── asgi.py
├── routes/
│   ├── __init__.py
│   ├── api.py
│   ├── console.py
│   └── web.py
├── config/
│   ├── __init__.py
│   ├── app.py.tmpl         # has {{ project_name }} token
│   └── database.py
├── app/
│   ├── __init__.py
│   ├── Http/
│   │   ├── __init__.py
│   │   ├── Controllers/__init__.py
│   │   └── Middleware/__init__.py
│   ├── Models/__init__.py
│   ├── Providers/__init__.py
│   └── Services/__init__.py
├── database/
│   ├── __init__.py
│   ├── migrations/.gitkeep
│   └── seeders/__init__.py
├── storage/.gitkeep
├── tests/
│   ├── __init__.py
│   ├── Feature/__init__.py
│   └── Unit/__init__.py
├── _dot_env_example         # → .env.example at copy time
├── _dot_gitignore           # → .gitignore at copy time
├── README.md.tmpl           # has {{ project_name }}, {{ project_name_pascal }}
└── pyproject.toml.tmpl      # has all three tokens
```

Two renaming rules at copy time:
- `*.tmpl` → strip `.tmpl` and apply token substitution.
- `_dot_*` → rename to `.<rest>` (Python packaging tooling refuses to
  include filenames starting with `.` in wheel data).

### Typer 0.19+ pin

Installer's `pyproject.toml` declares `typer >= 0.19, < 0.20`. We pin to the
minor for now (the Typer API is stable but not 1.0). Verified `0.19.x` as
the current latest stable per `100-coding-standards.mdc` § Dependency
Version Pinning.

### Token dict

```python
TOKENS = {
    "{{ project_name }}": <user input, validated>,
    "{{ project_name_pascal }}": <PascalCase of project_name>,
    "{{ python_version }}": <from --python flag or sys.version_info>,
}
```

The substitution function asserts that no `{{ ... }}` patterns remain in any
file post-substitution (catches typos in template files at install time,
not at user runtime).

## Consequences

**Positive**:
- `pipx run arvel-cli new my-app` works offline after first install.
- Skeleton version is exactly aligned with the installer version that
  produced it — no skew between "the installer I ran" and "the skeleton it
  used".
- Token substitution surface is tiny and reviewable (~5 lines of code).
- Typer choice means the same CLI patterns and helpers carry into WI-005's
  `arvel` console binary.

**Negative**:
- Wheel ships with the skeleton tree embedded. Current size ~5 KB total —
  negligible.
- `*.tmpl` and `_dot_*` renaming is two extra rules to remember when adding
  files. Mitigated by the post-copy assertion that no unsubstituted tokens
  remain, and by Gate #29 (no-unsubstituted-tokens) which audits the
  generated tree in CI.

**Enforcement**:
- `make smoke-skeleton` (Gate #7) generates a project end-to-end in CI.
- Adversarial path-traversal test suite (Gate #27, Stage 4b focus) covers
  malicious project names.
- New Gate #29 (Skeleton no-unsubstituted-tokens) greps the generated tree
  for `{{ ` after generation and fails the build if any token remains.
