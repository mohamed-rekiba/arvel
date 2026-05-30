# Database: Getting Started

Arvel supports raw SQL, a fluent [QueryBuilder](queries.md), and the full [ORM](arvent.md) — all backed by SQLAlchemy 2's async engine.

## Configuration

```env
DB_URL=postgresql+asyncpg://user:pass@127.0.0.1:5432/myapp
DB_POOL_SIZE=10
DB_POOL_RECYCLE=1800
DB_ECHO=false
```

Arvel uses SQLAlchemy 2 (async) under the hood, so any URL scheme SQLAlchemy supports works:

| Database | Scheme | Driver |
|---|---|---|
| SQLite | `sqlite+aiosqlite://` | `arvel[sqlite]` |
| PostgreSQL | `postgresql+asyncpg://` | `arvel[postgres]` |
| MySQL / MariaDB | `mysql+aiomysql://` | `arvel[mysql]` |

For SQLite:

```env
DB_URL=sqlite+aiosqlite:///database/database.sqlite
```

## Connecting

Connections are managed by the framework. You don't open or close them — request handlers and jobs receive a request-scoped session via the container.

```python
from arvel.facades import DB


users = await DB.table("users").get()
```

## The `DB` facade

For quick reads and writes without involving models:

```python
# Select
users = await DB.table("users").where("active", True).get()
user = await DB.table("users").where("id", 42).first()

# Insert
await DB.table("users").insert({"name": "Alice", "email": "a@b.com"})

# Update
await DB.table("users").where("id", 42).update({"name": "Alicia"})

# Delete
await DB.table("users").where("id", 42).delete()

# Aggregate
count = await DB.table("users").where("active", True).count()
```

See [Query Builder](queries.md) for the fluent API in depth.

## Raw queries

When the query builder doesn't fit, write raw SQL:

```python
results = await DB.select(
    "SELECT id, name FROM users WHERE created_at >= :since",
    {"since": last_week},
)
```

**Always parameterize.** Never interpolate user input into SQL strings — that's a SQL-injection waiting to happen. Arvel's query builder makes this structurally impossible (every value becomes a bound parameter); the raw `DB.select` API enforces it.

## Transactions

```python
async with DB.transaction():
    await User.create(...)
    await Audit.create(...)
```

If anything inside the block raises, the transaction rolls back. If it completes, it commits.

For nested transactions, Arvel uses savepoints (see ADR-043):

```python
async with DB.transaction():
    await User.create(...)
    async with DB.transaction():
        await Audit.create(...)  # savepoint
```

The inner block can roll back independently without aborting the outer transaction.

### Retry on deadlock

`DB.transaction()` is a context manager, so it can't re-run its body. For work that should
retry on a deadlock or serialization failure, pass a callback to `DB.transactional`:

```python
async def place_order(session) -> Order:
    order = await Order.create(...)
    await Inventory.where("sku", sku).decrement("qty", 1)
    return order


order = await DB.transactional(place_order, attempts=3)
```

Each attempt opens a fresh transaction. Only deadlock/serialization errors retry; anything
else (integrity violations, app errors) propagates immediately.

### Imperative control

When the begin/commit points don't line up with a block, drive the transaction by hand:

```python
await DB.begin_transaction()
try:
    await User.create(...)
    await DB.begin_transaction()   # SAVEPOINT
    await Audit.create(...)
    await DB.commit()              # release the savepoint
    await DB.commit()              # commit the outer transaction
except Exception:
    await DB.rollback()
    raise
```

Nested `begin_transaction()` calls (and calls inside a `DB.transaction()` block) open
savepoints, mirroring the context-manager behavior. `after_commit` callbacks registered
during an imperative transaction fire when the outermost `commit()` succeeds.

## Request-scoped transactions

For HTTP endpoints that should be all-or-nothing, use the `DatabaseTransaction` middleware:

```python
from arvel.http.middleware import DatabaseTransaction


@Route.post("/orders", middleware=[DatabaseTransaction()])
async def create(form: CreateOrder) -> dict:
    order = await Order.create(...)
    await OrderItem.create_many(...)
    return order.to_dict()
```

The middleware opens a transaction on entry, commits on a 2xx response, and rolls back on a 5xx or unhandled exception. See ADR-016 for why this is the **only** sanctioned bridge between `arvel.http` and `arvel.database`.

## Query logging

For development, enable query logging:

```env
DB_ECHO=true
```

Every query and its parameters print to the log. **Don't enable this in production** — query logs can contain sensitive data.

For structured per-query logging with timing, register `QueryLoggingServiceProvider` in your bootstrap:

```python
from arvel.database.query_logging import QueryLoggingServiceProvider

# Log every query
app.register(QueryLoggingServiceProvider)

# Log only queries that exceed 100 ms
app.register(QueryLoggingServiceProvider, slow_query_ms=100)
```

Each query emits a structlog record with three fields:

```json
{"event": "sql_query", "sql": "SELECT ...", "duration_ms": 3.7, "slow": false}
```

- `sql` — the rendered statement (bind parameters redacted)
- `duration_ms` — wall-clock time for the database round-trip
- `slow` — `true` when `duration_ms` exceeds the `slow_query_ms` threshold

When `slow_query_ms > 0`, only slow queries are logged. The default (`slow_query_ms=0`) logs everything. `DB_ECHO` and `QueryLoggingServiceProvider` are independent — both can be active at the same time.

## Multiple connections

For read replicas or sharded databases, register additional connections:

```env
DB_CONNECTIONS_READ_URL=postgresql+asyncpg://reader@db.internal/myapp
DB_CONNECTIONS_ANALYTICS_URL=postgresql+asyncpg://analytics@db.internal/warehouse
```

Use them via name:

```python
slow_query = await DB.connection("read").select("SELECT ...")
```

## Where to next?

- [Query Builder](queries.md) — fluent builder API.
- [Migrations](migrations.md) — schema management.
- [Pagination](pagination.md) — paginating result sets.
- [ORM](arvent.md) — when you want the full Active Record experience.
