# SQL Views & Functions

Some logic belongs in the database. A **view** gives a complex query a name so the rest of your app
reads from it like a table; a **materialized view** caches that query's result for fast reads on
expensive aggregations; a **stored function** runs a computation server-side. arvel lets you declare
all three as Python classes and create them from a migration, so they live in version control next to
the tables they depend on — not as loose SQL someone ran by hand once.

!!! note "Postgres-only DDL degrades loudly, not silently"
    Materialized views, `CREATE EXTENSION`, and GIN/GiST indexes are **Postgres-only**. On another
    dialect (sqlite/mysql) `Schema` emits a `postgres_only_feature` warning and degrades sensibly — a
    materialized view becomes a **plain view** (live, not materialized — so skip `REFRESH MATERIALIZED
    VIEW` off Postgres), an extension is **skipped**, and GIN/GiST become a plain index — so the same
    migration runs everywhere and your logs say what happened. Check `schema.dialect` to branch.

## Views

Declare a view as a `View` subclass with a `name` and a `query` (an arvel query builder, or a raw
SQL string), then create it from a migration:

```python
from arvel.database.schema import View

class ActiveUsers(View):
    name  = "active_users"
    query = User.where(active=True).select("id", "name", "last_seen_at")


class CreateActiveUsersView(Migration):
    def up(self, schema):
        schema.execute(ActiveUsers().create())    # CREATE VIEW active_users AS SELECT …

    def down(self, schema):
        schema.execute(ActiveUsers().drop())
```

For a one-off view you don't need a class for, the migration `schema` exposes `create_view` directly:

```python
def up(self, schema):
    schema.create_view("active_users", User.where(active=True).select("id", "name"))
```

Read from a view through a **read-only model** — point it at the view with `__view__` and any write
path raises `ReadOnlyModelError`, because a view has no table of its own to write to:

```python
class ActiveUser(Model):
    __view__ = "active_users"        # read-only: save()/delete()/touch() raise ReadOnlyModelError

recent = await ActiveUser.where("last_seen_at", ">", cutoff).get()   # queries the view
```

## Materialized views

A materialized view stores the query's *result* on disk, so reads are instant — the tradeoff is the
data is a snapshot, stale until you refresh it. Use one for a dashboard aggregate that's expensive to
compute and fine to be a few minutes behind:

```python
from arvel.database.schema import MaterializedView

class MonthlyRevenue(MaterializedView):
    name    = "monthly_revenue"
    query   = Order.select_raw("date_trunc('month', created_at) AS month, sum(total) AS revenue") \
                   .group_by("month")
    refresh = "concurrently"         # REFRESH … CONCURRENTLY — doesn't lock out readers


class CreateMonthlyRevenue(Migration):
    def up(self, schema):
        schema.execute(MonthlyRevenue().create())
```

Refresh it whenever the underlying data has moved on — from a [scheduled command](../console.md),
after a nightly import, or on demand. `refresh_op()` builds the statement; run it with `db.execute`:

```python
await db.execute(MonthlyRevenue().refresh_op())     # REFRESH MATERIALIZED VIEW [CONCURRENTLY]
await db.refresh_materialized_view("monthly_revenue", concurrently=True)   # same, by name
```

`refresh = "concurrently"` builds a `REFRESH … CONCURRENTLY`, which rebuilds the view without blocking
concurrent reads (Postgres requires a unique index on the view for this — declare it in `indexes`).
On sqlite/mysql the materialized view was created as a *plain* view, which is always live — there's
nothing to refresh, so skip `refresh_op()` there (branch on `schema.dialect` if the migration runs on
mixed backends).

## Stored functions

Declare a database function as a `DatabaseFunction` subclass — `body` is the function's SQL/PLpgSQL
source — and create it in a migration alongside everything else:

```python
from arvel.database.schema import DatabaseFunction

class IncrementBalance(DatabaseFunction):
    name    = "increment_balance"
    args    = [("account_id", "int"), ("amount", "numeric")]
    returns = "numeric"
    body    = """
        UPDATE accounts SET balance = balance + amount WHERE id = account_id;
        SELECT balance FROM accounts WHERE id = account_id;
    """


def up(self, schema):
    schema.execute(IncrementBalance().create())     # CREATE OR REPLACE FUNCTION …
```

Call it and get its scalar result back with `db.call_function` — the function name goes through
SQLAlchemy's `func` registry, never string-interpolated, so it's injection-safe:

```python
balance = await db.call_function("increment_balance", account_id=7, amount=100)
```

Arguments are passed positionally to the SQL function in the order given (keyword args keep their
declared order), and the result is the function's single returned value.

## Common mistakes & gotchas

- **Writing through a `__view__` model.** It's read-only by design — `save`/`delete`/`touch`/`restore`
  raise `ReadOnlyModelError`. Write to the model backing the underlying table instead.
- **`await`-ing `refresh_op()` directly.** `refresh_op()` (like `create()`/`drop()`) *builds* a
  statement — run it with `await db.execute(...)`, don't await the builder itself.
- **`refresh_op()` off Postgres.** A materialized view degrades to a live plain view on sqlite/mysql;
  there's nothing to refresh and `REFRESH MATERIALIZED VIEW` isn't valid SQL there.
- **`CONCURRENTLY` without a unique index.** Postgres rejects a concurrent refresh unless the
  materialized view has a unique index — add one via `indexes` on the class.
- **Interpolating into a raw view query.** A `View.query` string is emitted as-is; keep user input out
  of it and prefer a builder query, which parameterizes for you.

## How it works

The declarative classes (`View`, `MaterializedView`, `DatabaseFunction`) resolve their `query`/`body`
to a `sqlalchemy.text(...)` DDL statement via `.create()`/`.drop()`/`.refresh_op()`; the migration
runs it with `schema.execute(...)`. The `schema.create_materialized_view`/`create_extension` helpers
check `schema.dialect` and downgrade (with a warning) on non-Postgres backends, so one migration is
portable. `db.call_function` builds a `SELECT func.<name>(...)` through SQLAlchemy's function registry
rather than formatting the name into a string.

## See also

- [Queries](queries.md) — the builder that supplies a view's `query` and `select_raw`.
- [JSON, Full-Text & Vectors](json-search.md) — GIN/GiST indexes and Postgres extensions.
- [Migrations & Schema](migrations.md) — where views and functions are created.
- [Transactions & Streaming](transactions.md) — `db.select`/`db.statement` for raw SQL from app code.
