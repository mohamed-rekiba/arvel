# Database: Getting Started

Almost every modern web application interacts with a database. arvel makes connecting to databases and
running queries extremely simple across a variety of supported backends, using an async SQLAlchemy
core under the hood. You can talk to the database three ways: the fluent [query builder](queries.md),
the [ORM](index.md), and — for everything else — **raw SQL** through the `DB` facade.

Currently arvel supports these databases: PostgreSQL, MySQL/MariaDB, and SQLite.

## Configuration

Database configuration lives in `config/database.py`. There you define every connection and pick the
default. A fresh app ships one SQLite connection:

```python
# config/database.py
from arvel import env

config = {
    "default": env("DB_CONNECTION", "sqlite"),
    "connections": {
        "sqlite": {"url": env("DATABASE_URL", "sqlite+aiosqlite:///database/database.sqlite")},
    },
}
```

Each connection's `url` is a SQLAlchemy async URL (`postgresql+asyncpg://…`, `mysql+aiomysql://…`,
`sqlite+aiosqlite://…`). Add more named connections and select one per query with `name=` /
`connection=`.

### Read & write connections

Sometimes you want a separate connection for `SELECT`s (a read replica) and another for writes. Give a
connection `read` and `write` blocks instead of a flat `url`:

```python
"pgsql": {
    "read":  {"url": env("DB_READ_URL")},
    "write": {"url": env("DB_WRITE_URL")},
    "sticky": True,     # after a write, reads in the same request go to the writer
}
```

`sticky` keeps a request that has just written reading from the **writer** for the rest of that async
context, so it never reads its own not-yet-replicated write.

## Running SQL queries

Reach for raw SQL through the `DB` facade. `select` returns rows; parameters are bound (never
interpolated), so it's injection-safe:

```python
from arvel import DB

rows  = await DB.select("SELECT * FROM users WHERE active = :active", {"active": True})
one   = await DB.fetch_one(users_stmt)
count = await DB.scalar("SELECT count(*) FROM users")
```

For writes and DDL, use `statement` / `execute`:

```python
await DB.statement("UPDATE users SET active = true WHERE id = :id", {"id": 7})
```

When you want a builder but not a full model — a reporting query, a table with no `Model` — reach for
`DB.table(...)`:

```python
await DB.table("users").where(active=True).get()      # the query builder over a raw table
```

Stream a large result set row-by-row with `DB.stream(...)`, and call a stored SQL function with
`DB.call_function("my_fn", arg1, arg2)`.

## Database transactions

Run a set of operations atomically with `DB.transaction()` — anything raised inside rolls the whole
block back; nested blocks become savepoints:

```python
async with DB.transaction():
    await DB.table("accounts").where(id=1).decrement("balance", 100)
    await DB.table("accounts").where(id=2).increment("balance", 100)
```

`DB.transact(callback, attempts=3)` runs a callback in a transaction with automatic **retry** on
deadlock/serialization failures. See [Transactions & Streaming](transactions.md) for the full picture.

## Inspecting the connection

```python
DB.dialect()          # "postgresql" | "sqlite" | "mysql" — the active connection's backend
DB.enable_query_log() # start recording executed queries…
await run_some_work()
DB.get_query_log()    # …and read them back (great in tests)
```

## See also

- [Query Builder](queries.md) — the fluent builder for most queries.
- [ORM: Getting Started](index.md) — defining models over your tables.
- [Transactions & Streaming](transactions.md) — retries, savepoints, streaming reads.
- [Migrations](migrations.md) — creating and evolving the schema.
