# ADR-018 — Canonical application layout

**Status**: Accepted (amended 2026-05-17 — lowercase all directories)
**Date**: 2026-05-17
**Anchors**: Constitution Article X — Canonical Application Layout

## Context

Arvel's contract with users is "Laravel for Python", but until WI-004 there
flat smoke test that bound a route inline in `app/main.py` — useful for
testing framework primitives, useless as a reference shape for users.

This created three concrete problems:

1. **No reference shape for new users.** "Laravel-like" was a marketing claim,
   not a verifiable structure.
2. **Every framework feature had to be configured inline.** Without a
   `bootstrap/`, `routes/`, or `config/` convention, users would invent their
   own layouts.
3. **No installer scaffold to ship.** WI-004 needs to ship
   `pipx run arvel-cli new my-app`, and that command needs a canonical
   tree to copy.

Three layout options were considered:

| Option | Pros | Cons |
|---|---|---|
| A. Mirror Laravel 1-for-1 (incl. PHP-isms like `App\Http\Kernel`) | Maximum familiarity for Laravel devs | Some directories don't translate (no `Resources/views`, no Blade) |
| B. **Pythonic lowercase layout** (snake_case files, all-lowercase directories under `app/`) | Idiomatic Python, PEP 8 compliant, familiar enough to Laravel devs | Slightly different from Laravel — needs documentation |
| C. Custom Arvel-native layout | Free to design anything | Defeats the framework's stated positioning |

## Decision

**Option B** — fully Pythonic lowercase layout, ratified into the constitution
as Article X.

The top-level structure for every generated Arvel project:

```
my-app/
├── bootstrap/
│   ├── __init__.py
│   ├── app.py              # create_application() — the only composition root
│   └── providers.py        # top-level providers = [...] list
├── public/
│   ├── __init__.py
│   └── asgi.py             # asgi = create_application().into_asgi()
├── routes/
│   ├── __init__.py
│   ├── api.py
│   ├── console.py
│   └── web.py
├── config/
│   ├── __init__.py
│   ├── app.py
│   ├── database.py
│   └── …
├── app/
│   ├── __init__.py
│   ├── http/
│   │   ├── __init__.py
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
│   └── .gitkeep
├── tests/
│   ├── __init__.py
│   ├── feature/
│   └── unit/
├── .env.example
├── .gitignore
├── README.md
├── pyproject.toml
└── uv.lock
```

Conventions:
- **All directories**: lowercase (PEP 8). No PascalCase directory names anywhere.
- **Filenames everywhere**: snake_case (`app.py`, `database.py`, `user_controller.py`).
- **IDs**: UUID v7 everywhere — time-sortable, lexicographically ordered, no sequential enumeration.
- **Composition root contract**: `bootstrap/app.py::create_application()` is
  the only function that constructs an `ApplicationBuilder`.

The previous ADR rationale included a preference for PascalCase subdirs under `app/`
to mirror Laravel exactly. This was revised: Python's PEP 8 mandates lowercase
package names, and the cognitive benefit of matching Laravel's `App\Http\Controllers`
does not outweigh the inconsistency with Python conventions.

Changes to this layout are **breaking** per Article X §7 and require a major
version bump after 1.0.

## Consequences

**Positive**:
- Fully PEP 8 compliant. `from app.http.controllers.user_controller import UserController` is idiomatic Python.
- No special-casing needed in linters or import checkers.
- New users have one obvious shape, copied verbatim from the installer.

**Negative**:
- Diffs for projects started before this amendment show renames, not pure additions.

**Enforcement**:
- The skeleton in `arvel-cli` is the authoritative source.
- CI smoke test (NFR-004-006, Gate #7) verifies that `arvel new` produces the expected tree.
