# Configuration

Good configuration should feel boring: one obvious place for secrets, one obvious place for defaults, and no guessing which environment you are in. Arvel leans on **Pydantic Settings** for that—environment variables drive typed models, `.env` files load in a predictable order, and your app code receives a single composed picture at boot. This page walks through how that works for the root app, the database, the cache, and everything else you wire through the container.

## Environment-based settings

The root settings class is **`AppSettings`** (`arvel.app.config`). It extends Pydantic’s `BaseSettings` and maps fields from environment variables. By convention, root app keys use the **`APP_`** prefix (for example `APP_NAME`, `APP_ENV`, `APP_DEBUG`).

```python
from arvel.app.config import AppSettings

# Typically constructed for you during application bootstrap; values come from
# the environment and optional .env files.
settings = AppSettings()
print(settings.app_name, settings.app_env, settings.app_debug)
```

`AppSettings` also carries FastAPI metadata—description, version, docs URLs—so your OpenAPI surface and runtime config stay in sync. Set `APP_DESCRIPTION`, `APP_VERSION`, `APP_DOCS_URL`, and friends when you want to customize what appears in `/docs` without touching framework internals.

## `.env` file support

Arvel resolves a small stack of env files relative to your project root:

1. **`.env`** — shared defaults for every machine.
2. **`.env.{environment}`** — overlay when it exists (for example `.env.production` when `APP_ENV` is `production`).

Real environment variables always win over file contents, which matches how you expect twelve-factor apps to behave in CI and on servers.

A minimal local file might look like this:

```bash
APP_NAME=My App
APP_ENV=development
APP_DEBUG=true
APP_KEY=replace-with-a-long-random-secret
```

Keep production secrets out of git: commit **`.env.example`** with dummy values, and inject real values via your host or secret manager.

## Database configuration

Database settings live in **`DatabaseSettings`** (`arvel.data.config`). They use the **`DB_`** prefix. You can supply a single URL or structured fields—Arvel builds the async SQLAlchemy URL for you.

```bash
# Option A: explicit URL (wins when set)
DB_URL=postgresql+asyncpg://user:pass@localhost:5432/mydb

# Option B: structured fields
DB_DRIVER=postgres
DB_HOST=127.0.0.1
DB_PORT=5432
DB_DATABASE=mydb
DB_USERNAME=myuser
DB_PASSWORD=secret
```

In code, module settings are composed with the rest of the framework configuration; your repositories and migrations read the resolved URL from the same typed object, so dev and prod do not drift silently.

## Cache configuration

**`CacheSettings`** (`arvel.cache.config`) uses the **`CACHE_`** prefix. The default driver is in-memory; switch to Redis when you install the `redis` extra and point the URL at your instance.

```bash
CACHE_DRIVER=redis
CACHE_REDIS_URL=redis://localhost:6379/0
CACHE_DEFAULT_TTL=3600
CACHE_PREFIX=myapp:
```

## Accessing configuration values

How you touch settings depends on context:

- **At bootstrap**, the framework loads `AppSettings` together with module settings (database, cache, mail, sessions, and others registered in the default set). Project-level Python files under `config/` can supply defaults and exports—see `load_config` in `arvel.foundation.config` for the full merge rules.
- **In application code**, prefer **dependency injection**: accept `AppSettings` or a specific `ModuleSettings` subclass in constructors or FastAPI dependencies so values stay testable and explicit.

```python
from arvel.app.config import AppSettings

class HealthService:
    def __init__(self, config: AppSettings) -> None:
        self._config = config

    def environment_label(self) -> str:
        return self._config.app_env
```

Avoid reading `os.environ` directly for values that already exist on a settings model—you lose validation, defaults, and the single source of truth.

That is the configuration story: typed, layered, and friendly to `.env` files. When you are ready to see how those files sit next to routes and modules, continue to [Directory structure](directory-structure.md).
