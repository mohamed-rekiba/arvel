# Database: Getting Started

The database layer follows Arvel’s async-first rhythm. You configure a single connection (or compose URLs from structured settings), and every query flows through SQLAlchemy 2.0’s async engine and session — no blocking calls on the hot path.

This page walks through wiring up SQLite for local work, PostgreSQL or MySQL when you are ready to grow, and how those choices surface in your environment and settings.

## Configuration through settings

Database options live on `DatabaseSettings` (`arvel.data.config`). They load from environment variables with the `DB_` prefix, which keeps secrets out of code and plays nicely with `.env` files in development.

You can either set `DB_URL` to a full SQLAlchemy URL, or let Arvel build one from `DB_DRIVER`, host, port, database name, and credentials.

```python
# Typical .env fragments (not exhaustive)

# Option A — explicit URL (async drivers)
DB_URL=postgresql+asyncpg://user:pass@127.0.0.1:5432/myapp

# Option B — structured SQLite (default)
DB_DRIVER=sqlite
DB_DATABASE=database/database.sqlite

# Option C — structured PostgreSQL
DB_DRIVER=postgresql
DB_HOST=127.0.0.1
DB_PORT=5432
DB_DATABASE=myapp
DB_USERNAME=arvel
DB_PASSWORD=secret
```

The `url` property resolves a single connection string: SQLite paths are normalized for `sqlite+aiosqlite`, PostgreSQL family drivers use `postgresql+asyncpg`, and MySQL uses `mysql+aiomysql`.

## Supported drivers

Arvel expects **async** dialects in normal operation:

- **SQLite** — `sqlite+aiosqlite`, ideal for tests and local prototypes. The default database file path is relative to your project unless you pass an absolute path.
- **PostgreSQL** — `postgresql+asyncpg` when built from structured settings; use `DB_DRIVER` values like `pgsql`, `postgres`, or `postgresql`.
- **MySQL** — `mysql+aiomysql` for the async stack.

If you paste a sync-only URL into `DB_URL`, the migration runner’s Alembic layer can still operate in a compatibility mode, but your application code should stay on async sessions for consistency.

## Pool and session defaults

Sensible defaults are already chosen: `pool_pre_ping` catches dead connections, `pool_recycle` avoids stale server-side disconnects, and `expire_on_commit=False` matches how Arvel expects you to read attributes after a unit of work completes — especially in async code where surprise lazy loads are unwelcome.

Tune `pool_size`, `pool_max_overflow`, and `pool_timeout` when you profile under load; the defaults mirror common SQLAlchemy guidance for modest web workloads.

## Registering the provider

In a full application, register `DatabaseServiceProvider` so models can resolve a default session via `ArvelModel.query()` without you threading `AsyncSession` through every call site. In tests, pass an explicit session to `Model.query(session)` or construct a `QueryBuilder` yourself — the API stays the same.

Once the URL is correct and the provider is registered, you are ready to define models, run migrations, and let the ORM handle the rest. The database chapter in this site goes deeper into migrations, the query builder, and pagination — but it all starts with this one connection string and a clear async story.
