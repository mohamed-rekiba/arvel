# Query Builder

<a name="introduction"></a>
## Introduction

Arvent's query builder provides a fluent interface for building and running database queries. Every query starts from a model and chains synchronous builder methods; an `async` terminal method runs the query and returns the result.

```python
items = await (
    Item.where(is_active=True)
    .where(Item.price < 100)
    .order_by("-created_at")
    .limit(20)
    .get()
)
```

`Item.where(...)` returns a `QueryBuilder`. Builder methods like `where`, `order_by`, and `limit` return the builder so you can chain. Terminal methods — `get`, `first`, `count`, `paginate` — execute against the active database session and must be awaited.

> [!NOTE]
> New to Arvent? Read [Models & CRUD](models.md) first, then [Relationships](relationships.md) for eager loading ([section overview](index.md)). Builder methods return a **new** builder rather than mutating in place, so a partially-built query is safe to reuse as a base for several variations.

<a name="running-queries"></a>
## Running Queries

<a name="retrieving-rows"></a>
### Retrieving Rows

| Method | Returns |
|---|---|
| `get()` / `all()` | All matching models (a `ModelCollection`) |
| `first()` | First model, or `None` |
| `first_or_fail()` | First model, or raises `ModelNotFoundError` |
| `first_where(**kwargs)` | First model matching the kwargs |
| `sole()` | Exactly one row (errors if zero or many) |
| `find(pk)` / `find_or_fail(pk)` | By primary key (respects scopes) |
| `value("col")` | A single column value from the first row |
| `pluck("col")` | A list of one column; `pluck("col", "key")` → dict |

```python
items = await Item.where(is_active=True).get()
first = await Item.where(is_active=True).first()
names = await Item.pluck("name")
```

`sole()` is the right tool when a query *must* match exactly one row — it raises `ModelNotFoundError` for zero and `MultipleResultsError` for more than one, so an ambiguous result fails loudly instead of silently picking the first:

```python
user = await User.where(email="ada@example.com").sole()
```

<a name="aggregates"></a>
### Aggregates

```python
total = await Item.where(is_active=True).count()
revenue = await Item.sum("price")     # empty result → 0
average = await Item.avg("price")
top = await Item.max("price")
floor = await Item.min("price")
exists = await Item.where(sku="ABC").exists()
none = await Item.where(sku="ABC").doesnt_exist()
```

<a name="where-clauses"></a>
## Where Clauses

<a name="the-where-method"></a>
### The where Method

`where` accepts several forms: keyword equality, the Laravel-style string form, or a SQLAlchemy column expression. Use keyword arguments for simple equality:

```python
await Item.where(is_active=True).get()
await Item.where(status="published", featured=True).get()   # AND
```

The string form mirrors Laravel — `where(column, value)` for equality, or `where(column, operator, value)` for any operator:

```python
await Item.where("status", "published").get()       # status = 'published'
await Item.where("price", "<", 100).get()            # price < 100
await Item.where("name", "ilike", "%ada%").get()     # case-insensitive LIKE
```

Valid operators: `=`, `!=`, `>`, `<`, `>=`, `<=`, `like`, `ilike`. `or_where` takes the same forms.

For comparisons other than equality, you can also pass a SQLAlchemy expression on the model's columns:

```python
await Item.where(Item.price < 100).get()
await Item.where(Item.views >= 1000).get()
```

<a name="or-where-clauses"></a>
### Or Where Clauses

Chain `or_where` to add an `OR` branch:

```python
await Item.where(is_active=True).or_where(Item.featured == True).get()
```

<a name="additional-where-clauses"></a>
### Additional Where Clauses

The builder offers a wide range of where variants. Most have an `or_*` sibling:

| Method | Example |
|---|---|
| `where_in` / `where_not_in` | `where_in("id", [1, 2, 3])` |
| `where_between` / `where_not_between` | `where_between("age", 18, 65)` |
| `where_null` / `where_not_null` | `where_null("deleted_at")` |
| `where_like` / `where_not_like` | `where_like("name", "%ada%", case_sensitive=False)` |
| `where_date` / `where_time` / `where_year` / `where_month` / `where_day` | date-part filters |
| `where_column` | compare two columns |
| `where_raw` | `where_raw("price > tax * :m", {"m": 10})` |
| `where_exists` | correlated `EXISTS` subquery |
| `where_json_path` / `where_json_contains` | PostgreSQL JSON filters |
| `where_full_text` | full-text search |
| `where_any` / `where_all` / `where_none` | apply an operator across several columns |
| `has` / `where_has` / `doesnt_have` / `where_relation` | filter by [related rows](relationships.md#querying-relationship-existence) |

`where_any` / `where_all` / `where_none` apply one operator across several columns — useful for a multi-column search box:

```python
# match the term in ANY of these columns
await Item.where_any(["name", "sku", "description"], "ilike", f"%{term}%").get()

# require a condition across ALL of them
await Order.where_all(["paid", "shipped"], "=", True).get()
```

<a name="logical-grouping"></a>
### Logical Grouping

To group conditions inside parentheses, pass a closure that returns the builder:

```python
await Item.where(is_active=True).where(
    lambda q: q.where(Item.price < 10).or_where(Item.featured == True)
).get()
```

This produces `WHERE is_active AND (price < 10 OR featured)`.

<a name="ordering-grouping-limit-offset"></a>
## Ordering, Grouping, Limit & Offset

```python
.order_by("created_at")      # ascending
.order_by("-created_at")     # descending (leading "-")
.order_by_desc("created_at")
.latest()                    # order_by created_at desc
.oldest()
.in_random_order()
.reorder("name")             # clear existing order, then re-apply
.limit(20)
.offset(40)
.group_by("status")
.having("total", ">", 100)   # the 3-arg operator form IS valid on having
.distinct()
```

> [!NOTE]
> Arvent uses `limit` / `offset`. There is no `take` / `skip` on the query builder (those names exist on the [`Collection`](#collections) wrapper instead).

<a name="selecting-and-joining"></a>
## Selecting & Joining

Select specific columns, or run joins with SQLAlchemy expressions:

```python
.select("id", "name")
.add_select("email")
.select_raw("COUNT(*) AS total")
.distinct("status")

# joins take a target model and an ON expression
.join(Post, Post.user_id == User.id)
.left_join(Post, Post.user_id == User.id)
```

> [!NOTE]
> Joins are expressed with SQLAlchemy column expressions, not the string `"table.col", "=", "table.col"` form. For ergonomic column-to-column joins, `join_on(Target, lambda on: ...)` is also available.

A `select()` of specific columns (or `select_raw`) returns a `Collection` of dict rows rather than a `ModelCollection` of models.

<a name="subqueries"></a>
## Subqueries

The builder composes with itself: build a query, then feed it into another as a subquery. `select_sub` adds a correlated scalar column, `from_sub` queries from a derived table, and `join_sub` joins against one:

```python
# correlated scalar: each user's latest post timestamp as a column
latest = Post.where_column("posts.user_id", "users.id").select_raw("MAX(created_at)")
users = await User.select("id", "name").select_sub(latest, "last_post_at").get()

# query from a derived table of pre-aggregated rows (comes back as dicts)
totals = (
    Order.select("user_id")
    .select_raw("SUM(total) AS revenue")
    .group_by("user_id")
    .having("revenue", ">", 1000)
)
big_spenders = await User.from_sub(totals, "t").get()

# join against a subquery — `on` receives the aliased subquery
await User.join_sub(totals, "t", lambda t: User.id == t.c.user_id).get()
```

For existence rather than a value, `where_exists` takes a closure that builds the correlated subquery:

```python
await User.where_exists(lambda q: q.where_column("orders.user_id", "users.id")).get()
```

<a name="conditional-clauses"></a>
## Conditional Clauses

Build queries from runtime conditions without breaking the chain. `when` runs the callback when the condition is truthy; `unless` runs it when falsy. This keeps request-driven filtering flat instead of a tangle of `if` statements:

```python
async def index(request):
    search = request.query_params.get("q")
    sort = request.query_params.get("sort")
    include_inactive = request.query_params.get("all") == "1"

    items = await (
        Item.query()
        .when(search, lambda q, value: q.where_like("name", f"%{value}%"))
        .when(sort, lambda q, value: q.order_by(value))
        .unless(include_inactive, lambda q: q.where(is_active=True))
        .paginate(15)
    )
    return items
```

The truthy value is passed as the second argument to the callback, so you don't have to close over it.

`tap` runs a side effect on the builder (logging, conditional mutation) and returns it so the chain continues:

```python
Item.query().tap(lambda q: logger.debug(q.to_sql())).where(is_active=True)
```

<a name="pagination"></a>
## Pagination

Arvent offers three paginators. The default `paginate` runs a `COUNT` so it knows the total and last page:

```python
page = await Item.where(is_active=True).paginate(per_page=15, page=2)

page.items            # the rows for this page (a list)
page.total            # total matching rows
page.current_page     # 2
page.last_page        # computed from total / per_page
page.has_more_pages   # bool
```

When handling an HTTP request, the page number is read from the request automatically — `paginate(15)` is enough.

<a name="paginator-output"></a>
### Paginator Output

Serialize a paginator with `to_dict()` (a `{data, meta, links}` envelope) or `to_response()` (a flat Laravel-style envelope). Pass a `base_url` to get URL links instead of bare page numbers:

```python
page.to_dict(base_url="https://api.example.com/items")
```

The idiomatic way to return a paginated list from an HTTP endpoint is to hand the paginator to a [resource collection](../the-basics/resources.md#resource-collections), which renders the standard envelope for you.

<a name="simple-and-cursor-pagination"></a>
### Simple & Cursor Pagination

For large datasets, skip the `COUNT`:

```python
# next/prev only, no total — lighter
page = await Item.simple_paginate(per_page=15)
page.has_more

# keyset cursor pagination — best for deep, stable scrolling
page = await Item.cursor_paginate(per_page=15, cursor=token)
page.next_cursor
page.prev_cursor
```

A cursor token is opaque — clients pass back whatever `next_cursor`/`prev_cursor` gave them. If a request arrives with a hand-edited or truncated `?cursor=`, decoding raises `InvalidCursorError`. The default HTTP wiring translates that to a `400 Bad Request` with a fixed message, so a malformed cursor never surfaces as a `500` or leaks the base64/JSON decode internals.

<a name="chunking-and-streaming"></a>
## Chunking & Streaming

To process large result sets without loading everything into memory:

```python
# iterate one row at a time
async for item in Item.lazy():
    ...

# process in batches; return False from the callback to stop early
await Item.chunk(500, process_batch)

# run a callback once per row across the whole result set
await Item.where(is_active=True).each(process_one)

# stable when the callback mutates rows that would shift offsets
await Item.chunk_by_id(500, process_batch)
```

> [!WARNING]
> When the callback **modifies** the column the query orders/filters on, plain `chunk` can skip or repeat rows as offsets shift. Reach for `chunk_by_id`, which paginates by the primary key instead of `OFFSET`.

<a name="bulk-writes"></a>
## Bulk Writes

The builder runs set-based writes that bypass per-row model events:

```python
await Item.where(is_active=False).update({"is_active": True})
await Item.insert([{...}, {...}])
new_id = await Item.insert_get_id({...})
await Item.upsert(rows, unique_by=["sku"], update=["price"])
await Item.where(...).increment("views")
await Item.where(...).decrement("stock", 2)
await Item.where(...).delete()        # soft delete if SoftDeletes, else hard
```

`update`, `delete`, `increment`, and `decrement` return the number of affected rows.

Get-or-create helpers cover the common idioms: `first_or_create`, `first_or_new`, `update_or_create`, `update_or_insert`.

> [!WARNING]
> Bulk writes operate at the SQL level and do **not** fire [model events](models.md#model-events) or run per-row casts. When you need events, load the models and save them individually.

<a name="transactions"></a>
## Database Transactions

Wrap several writes in a single atomic unit with `DB.transaction()`. If the block raises, everything rolls back; if it returns normally, it commits:

```python
from arvel.database import DB


async with DB.transaction():
    order = await Order.create(user_id=user.id, total=total)
    await user.decrement("credit", total)   # both land, or neither does
```

Nested `DB.transaction()` blocks open **savepoints** rather than a second physical transaction, so an inner failure can be caught and rolled back without aborting the outer one.

When you need automatic retries on a deadlock or serialization failure, use `DB.transactional` — each attempt runs in a fresh transaction:

```python
async def settle(session):
    await ledger.save()
    await payment.save()

await DB.transactional(settle, attempts=3)
```

To run work only after the transaction actually commits — dispatching an email, busting a cache — register it with `DB.after_commit`. The callback is skipped entirely if the transaction rolls back, and inside a savepoint it's deferred to the outermost commit:

```python
async with DB.transaction():
    user = await User.create(**data)
    DB.after_commit(lambda: send_welcome_email(user))
```

> [!NOTE]
> Inside an HTTP request wrapped by the `DatabaseTransaction` middleware you're already in a transaction, so `DB.after_commit(...)` works without an explicit `DB.transaction()` block.

<a name="raw-queries"></a>
## Raw Queries & the DB Facade

When you need to drop below the model layer — a reporting query, a table with no model, a one-off statement — the `DB` facade runs parameterized SQL and offers a lightweight table builder.

```python
from arvel.database import DB

rows = await DB.select(
    "SELECT status, COUNT(*) AS n FROM orders WHERE total > :min GROUP BY status",
    {"min": 100},
)                                           # list[dict]
count = await DB.scalar("SELECT COUNT(*) FROM orders")
await DB.statement("REINDEX TABLE orders")
```

> [!WARNING]
> Always pass values as **bindings** (`:name` placeholders + a dict), never by string-formatting them into the SQL. Bindings are escaped by the driver; interpolation opens a SQL-injection hole.

The table builder works on a bare table name without a model:

```python
await DB.table("audit_log").insert([{"action": "login", "user_id": 1}])
recent = await DB.table("audit_log").where("user_id", 1).order_by("created_at").limit(10).get()
await DB.table("sessions").where("expired", True).delete()
```

For a named connection, go through `DB.connection("analytics").select(...)`.

<a name="scopes"></a>
## Scopes

<a name="local-scopes"></a>
### Local Scopes

Local scopes are reusable query fragments you call by name. The preferred way is the `@scope` decorator stacked on a `@staticmethod`. The first parameter is the query builder — the framework injects it — and the resulting method exposes only your own arguments:

```python
from arvel.database import Model, Timestamps, QueryBuilder, id_, scope


class Post(Model, Timestamps):
    __tablename__ = "posts"
    id: int = id_()

    @scope
    @staticmethod
    def published(qb: QueryBuilder["Post"]) -> QueryBuilder["Post"]:
        return qb.where(status="published")

    @scope
    @staticmethod
    def of_author(qb: QueryBuilder["Post"], author_id: int) -> QueryBuilder["Post"]:
        return qb.where(user_id=author_id)


published = await Post.published().get()              # QB is created for you
mine = await Post.published().of_author(7).get()       # chains onto the live QB
```

Stacking `@staticmethod` keeps type checkers from treating the function as a regular method (so they don't complain about a missing `self`), and the decorated call type-checks with just the user-supplied arguments.

#### Without the decorator

If you'd rather skip the decorator, name a method `scope_<name>` and Arvent discovers it automatically. The signature is `(self, query, *args)` — the framework supplies a throwaway instance as `self`:

```python
class Post(Model, Timestamps):
    __tablename__ = "posts"
    id: int = id_()

    def scope_published(self, query: QueryBuilder["Post"]) -> QueryBuilder["Post"]:
        return query.where(status="published")
```

Both styles call the same way: `Post.published()`.

<a name="global-scopes"></a>
### Global Scopes

Global scopes apply to every query for a model — this is exactly how [soft deletes](models.md#soft-deleting) hide trashed rows. The simplest form is `add_global_scope` with a callable `(QueryBuilder) -> QueryBuilder`:

```python
Post.add_global_scope("tenant", lambda q: q.where(tenant_id=current_tenant()))
```

For anything beyond a one-liner, subclass `GlobalScope` and implement `apply`. `add_global_scope` takes either a `GlobalScope` instance or a callable:

```python
from arvel.database import GlobalScope, QueryBuilder


class TenantScope(GlobalScope):
    def apply(self, qb: QueryBuilder["Post"]) -> QueryBuilder["Post"]:
        return qb.where(tenant_id=current_tenant())


Post.add_global_scope("tenant", TenantScope())
```

The built-in `SoftDeleteScope` is a `GlobalScope` — the `SoftDeletes` mixin registers one on every soft-deleting model.

To attach scopes at class-definition time instead of a separate call, set `__arvel_global_scopes__`:

```python
class Post(Model, Timestamps):
    __tablename__ = "posts"
    __arvel_global_scopes__ = {"tenant": TenantScope().apply}
    id: int = id_()
```

Opt out per query by name, or drop them all:

```python
await Post.without_global_scope("tenant").get()
await Post.without_global_scopes().get()
```

<a name="collections"></a>
## Collections

Query results come back as a `ModelCollection` — a `list` subclass with fluent helpers. Because it's a list, ordinary iteration and indexing work, plus:

```python
items = await Item.where(is_active=True).get()

items.pluck("name")
items.map(lambda i: i.price)
items.filter(lambda i: i.price > 10)
items.first_where(sku="ABC")
items.group_by(lambda i: i.status)
items.key_by("id")
items.sum("price")              # sum by attribute name
items.only(1, 2, 3)            # members whose primary key is in the set
```

`sum` takes an attribute name, not a lambda. On a collection, `only(...)`/`except_(...)` filter **members by primary key** — to pick a subset of *columns* from a single model, use `item.only("id", "name")`, which returns a dict.

`ModelCollection` adds model-aware helpers on top: `model_keys()`, PK-aware `contains`/`find`, and `await items.load("relation")` to eager-load onto an existing collection.

> [!NOTE]
> The `Collection` filtering helper is `first_where(**kwargs)`, not a Laravel-style `where(...)`. There's no `where()` on collections.

<a name="debugging"></a>
## Debugging

Inspect the compiled SQL and bindings without running the query, or get the database's execution plan:

```python
print(Item.where(is_active=True).to_sql())        # SQL string
print(Item.where(is_active=True).get_bindings())   # bound parameters
plan = await Item.where(is_active=True).explain()  # EXPLAIN output
```

To audit what a whole block of code emits, turn on the query log. Every statement is captured with its bindings and timing:

```python
from arvel.database import DB

DB.enable_query_log()
await Item.where(is_active=True).get()
await Order.create(total=10)

DB.get_query_log()    # [{"sql": ..., "bindings": ..., "time_ms": ...}, ...]
DB.flush_query_log()  # clear it
DB.disable_query_log()
```

`DB.pretend` runs a block, captures the SQL it *would* emit, and rolls everything back so nothing persists — a dry run for a migration-like script or a risky bulk write:

```python
log = await DB.pretend(lambda: Item.where(is_active=False).delete())
# log holds the captured statements; the rows are untouched
```
