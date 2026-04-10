# Directory structure

Laravel developers often say the framework “feels like it knows where things go.” Arvel chases the same clarity: **sensible defaults, a single front door for the ASGI app, and folders that read like chapters of your product**—HTTP here, configuration there, persistence over there. You can always diverge when you need to, but starting from the conventional layout keeps onboarding short and code reviews fast.

## The layout at a glance

A project created with `arvel new` roughly follows this shape (names may vary slightly by template, but the spirit stays the same):

```text
my-app/
├── bootstrap/
│   └── app.py          # ASGI factory: create_app()
├── app/                # Application modules (domain code)
├── config/             # Python defaults for settings slices
├── routes/             # HTTP route registration (or feature routers)
├── database/           # Migrations, seeds, SQLite file (if used)
├── tests/              # Pytest suite
├── .env                # Local secrets (not committed)
├── pyproject.toml      # Dependencies (often managed by uv)
└── README.md
```

The CLI’s `arvel serve` command looks for **`bootstrap/app.py`** and imports **`create_app`** by default—so that file is the spine of your deployable unit.

## bootstrap/

This directory holds the **application factory**. `create_app()` is what uvicorn loads (with `factory=True`), and it is where you register routes, exception handlers, lifespan hooks, and anything else that must exist before the first request.

```python
# bootstrap/app.py (conceptual)
from arvel.foundation.application import Application

def create_app() -> Application:
    ...
```

Keeping bootstrap thin means your “wiring” stays obvious and your domain logic stays in `app/`.

## app/

Put **feature and domain code** here—services, actions, domain models that are not framework glue, and anything you want to import cleanly from routes or jobs. Think of `app/` as the home for code that would survive if you swapped HTTP for a CLI or a queue consumer tomorrow.

## config/

Typed defaults and optional Python-side overrides for settings classes live under **`config/`**—for example `config/app.py` for root `AppSettings` or per-module files that the loader discovers by convention. Use this layer when a value is the same for every developer but still belongs in version control (default pool sizes, non-secret feature flags).

## routes/

HTTP endpoints need a home. **`routes/`** (or route modules imported from here) is where you declare API surfaces, wire controllers, and apply middleware at a granular level. Smaller apps might use a single module; larger ones split by area (`routes/users.py`, `routes/billing.py`).

## database/

Migrations, factories, and seed scripts typically live alongside the database artifact. For SQLite during development, you will often see **`database/database.sqlite`** in the tree. Treat this directory as everything that answers: “What does the schema look like, and how do we reset or evolve it safely?”

## tests/

**`tests/`** mirrors production packages with pytest. Keep fixtures here, mark integration tests when they hit real services, and aim for names that read like specifications (`test_login_with_valid_token_returns_session`).

## Convention over configuration

Arvel’s philosophy is simple: **if you follow the paths above, tools work without flags.** The dev server discovers `bootstrap.app:create_app`. Environment files load in a fixed order. Module settings pick up `config/*.py` when present. When you need to break convention—say a monorepo sub-app—pass explicit options (`arvel serve --app`, custom template URLs on `arvel new`) rather than fighting the defaults silently.

That mental model should carry you from first clone to first deploy. For turning the same tree into production traffic, read [Deployment](deployment.md).
