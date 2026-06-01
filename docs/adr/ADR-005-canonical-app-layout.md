# ADR-005 — Canonical application layout

**Status**: Accepted (amended 2026-05-17 — lowercase all directories)
**Date**: 2026-05-17
**Last reconciled**: 2026-06-01
**Anchors**: Constitution Article X — Canonical Application Layout

## Context

Arvel's contract with users is "Laravel for Python", which needs one canonical project shape. Without a `bootstrap/`, `routes/`, or `config/` convention, users would invent their own layouts and "Laravel-like" would be a marketing claim rather than a verifiable structure. The CLI also needs a canonical tree to scaffold from.

Three options were considered: mirror Laravel 1-for-1 (familiar, but PHP-isms like `App\Http\Kernel` don't translate); a Pythonic lowercase layout (idiomatic, PEP 8, familiar enough); or a custom Arvel-native layout (defeats the positioning).

## Decision

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

## Consequences

**Positive**:
- Fully PEP 8 compliant; `from app.http.controllers.user_controller import UserController` is idiomatic.
- No special-casing in linters or import checkers.
- New users get one obvious shape, copied verbatim from the scaffolder.

**Negative**:
- Projects started before the lowercase amendment show renames.

## Current implementation

- Authoritative skeleton: `packages/arvel/src/arvel/_skeleton/` (rendered by `arvel new`).
- Loader contract: ADR-006.
- Docs: `docs-fresh/architecture/bootstrap-lifecycle.md`, `docs-fresh/console/cli-architecture.md`.

## Notes

- **Reconciled**: enforcement is no longer "the skeleton in `arvel-cli`". The skeleton is packaged inside `arvel` at `_skeleton/` and rendered by the `arvel new` command (ADR-126, ADR-126). A smoke test verifies `arvel new` produces the expected tree.
