# Query Builder

The `DB` facade and model classmethods both expose Arvel's typed `QueryBuilder[T]`. It composes SQLAlchemy `Select` statements under the hood, so anything you can express in SQLAlchemy you can express here — with a friendlier surface and full type safety.

## Selecting rows

```python
users = await DB.table("users").get()                 # list of dicts
first = await DB.table("users").first()               # single dict or None
user = await DB.table("users").where("id", 42).first()

# Model classmethods return typed instances
posts = await Post.all()                              # list[Post]
post = await Post.find(42)                            # Post | None
post = await Post.find_or_fail(42)                    # Post or raises
```

## Filtering

```python
# Equality (kwarg shorthand)
active_users = await User.where(active=True).get()

# Equality (operator form)
recent = await User.where("created_at", ">=", week_ago).get()

# IN
admins = await User.where_in("role", ("admin", "owner")).get()

# NOT IN
others = await User.where_not_in("role", ("admin",)).get()

# Range
adults = await User.where_between("age", (18, 64)).get()

# NULL checks
no_email = await User.where_null("email").get()
has_email = await User.where_not_null("email").get()

# Pattern matching
johns = await User.where("name", "LIKE", "John%").get()
```

The kwarg-shorthand form is preferred when you have a field name — it resolves through `getattr(Model, name)` and binds the value as a parameter. SQL injection is structurally impossible. See ADR-013.

## Combining conditions

```python
# Both must match (default; chained calls AND)
result = await (
    User.where(active=True)
    .where("age", ">=", 18)
    .get()
)

# Either (OR group)
result = await (
    User.where(active=True)
    .or_where("role", "admin")
    .get()
)

# Nested groups
result = await (
    User.where(active=True)
    .where(lambda q: q.where("role", "admin").or_where("role", "owner"))
    .get()
)
```

## Ordering, limiting, offsetting

```python
recent = await (
    Post.order_by("-created_at")     # leading "-" → descending
    .order_by("title")
    .limit(20)
    .offset(40)
    .get()
)
```

For pagination, prefer `.paginate(page, per_page)` — see [Pagination](pagination.md).

## Aggregates

```python
count = await User.count()
total = await Order.sum("total_cents")
avg   = await Order.avg("total_cents")
max_age = await User.max("age")
min_age = await User.min("age")
```

## Joins

```python
posts_with_authors = await (
    DB.table("posts")
    .join("users", "posts.author_id", "=", "users.id")
    .select("posts.*", "users.name as author_name")
    .get()
)
```

For relationship-aware joins, prefer Arvent:

```python
posts = await Post.with_("author").get()
```

See [ORM Relationships](arvent-relationships.md).

## Grouping

```python
counts_by_role = await (
    DB.table("users")
    .group_by("role")
    .select("role", DB.raw("COUNT(*) as user_count"))
    .get()
)
```

## Subqueries and `EXISTS`

```python
result = await (
    User.where_exists(
        lambda q: q.from_("orders").where("orders.user_id", "=", DB.raw("users.id")),
    )
    .get()
)
```

## Raw expressions

For SQL fragments you can't express via the builder, use `DB.raw`:

```python
top_buyers = await (
    User.select("users.*", DB.raw("(SELECT COUNT(*) FROM orders WHERE orders.user_id = users.id) as order_count"))
    .order_by(DB.raw("order_count DESC"))
    .limit(10)
    .get()
)
```

`DB.raw` strings are **not** parameterized — only use them with hard-coded SQL. Never interpolate user input.

## Inserts and updates

```python
# Insert
new_id = await DB.table("users").insert_get_id({
    "name": "Alice",
    "email": "alice@example.com",
})

# Bulk insert
await DB.table("users").insert([
    {"name": "Bob", "email": "bob@example.com"},
    {"name": "Carol", "email": "carol@example.com"},
])

# Update
affected = await DB.table("users").where(active=False).update({"active": True})

# Upsert
await DB.table("users").upsert(
    [{"email": "alice@example.com", "name": "Alice"}],
    unique_by=["email"],
    update=["name"],
)
```

## Deletes

```python
deleted = await DB.table("users").where(active=False).delete()
```

## Column selection

By default every query selects all columns. Use `select()` to restrict:

```python
users = await User.select("id", "name", "email").get()
```

`select_raw()` accepts a literal SQL fragment when you need a computed column:

```python
users = await User.select_raw("id, name, LENGTH(bio) AS bio_len").get()
```

## Distinct

```python
roles = await User.distinct("role").pluck("role")
```

Without arguments, `distinct()` applies `SELECT DISTINCT` to the whole row.

## Ordering shortcuts

```python
recent    = await Post.latest().get()            # ORDER BY created_at DESC
oldest    = await Post.oldest().get()            # ORDER BY created_at ASC
recent_by = await Post.latest("published_at").get()
```

## Grouping and HAVING

```python
counts = await (
    DB.table("orders")
    .group_by("status")
    .having(DB.raw("COUNT(*) > 5"))
    .select("status", DB.raw("COUNT(*) as total"))
    .get()
)

# Raw HAVING with a bound parameter
big_spenders = await (
    DB.table("orders")
    .group_by("user_id")
    .having_raw("SUM(total_cents) > :min", {"min": 100_000})
    .select("user_id", DB.raw("SUM(total_cents) as spent"))
    .get()
)
```

## Single-value retrieval

```python
name  = await User.where(id=1).value("name")     # Any | None
roles = await User.pluck("role")                  # list[Any]
```

`value()` returns the first row's column. `pluck()` returns that column for every row.

## Strict first

`sole()` raises `MultipleResultsFound` if the query matches more than one row — useful when you expect exactly one:

```python
token = await ApiToken.where(hash=h).sole()
```

## First-or fallback

```python
guest = await User.where(email=email).first_or(lambda: User(role="guest"))
```

## Conditional query construction

`when()` applies a callback only when a condition is truthy — keeps builder chains clean when dealing with optional filters:

```python
qb = User.where()
qb = qb.when(search, lambda q, v: q.where("name", "LIKE", f"%{v}%"))
qb = qb.when(role,   lambda q, v: q.where(role=v))
users = await qb.get()
```

## Column-to-column comparison

```python
discounted = await Product.where_column("price", "compare_price").get()
# → WHERE price < compare_price (uses < by default)

# Explicit operator:
overdue = await Order.where_column("due_at", "<", "shipped_at").get()
```

## Multi-column OR match

`where_any()` applies a single condition across multiple columns with OR:

```python
results = await User.where_any(["name", "email", "username"], "LIKE", "%alice%").get()
# → WHERE (name LIKE '%alice%' OR email LIKE '%alice%' OR username LIKE '%alice%')
```

## Raw WHERE clause

When no builder method fits, drop to a parameterised raw fragment:

```python
active = await User.where_raw("status = :s AND score > :min", {"s": "active", "min": 50}).get()
```

Never interpolate user input into the raw string — always use bind parameters.

## Raw ORDER BY

```python
ordered = await Post.order_by_raw("FIELD(status, 'pinned', 'active', 'archived')").get()
```

## UNION and UNION ALL

```python
admins  = User.where(role="admin")
editors = User.where(role="editor")

combined = await admins.union(editors).get()           # deduplicates
all_rows = await admins.union_all(editors).get()       # keeps duplicates
```

## Pessimistic locking

```python
async with DB.transaction():
    seat = await Seat.where(id=seat_id).lock_for_update().first()
    # row is locked until the transaction commits
    seat.status = "reserved"
    await seat.save()
```

## Increment and decrement

```python
await Post.where(id=post_id).increment("views")
await Post.where(id=post_id).increment("score", 5)
await Inventory.where(sku=sku).decrement("stock")
```

These are atomic — they translate to `UPDATE ... SET col = col + n`.

## Update-or-insert

`update_or_insert` finds a row by `where` and updates it, or inserts it if it doesn't exist:

```python
await DB.table("settings").update_or_insert(
    where={"key": "theme"},
    values={"value": "dark"},
)
```

## Streaming and chunking

For large result sets, avoid loading everything into memory at once:

```python
# Callback per batch of 1 000
async def handle_batch(batch: list[User]) -> None:
    for user in batch:
        await process(user)

await User.chunk(1000, handle_batch)

# Item-by-item callback
await User.each(process)
```

`each()` calls the callback once per row; internally it chunks in batches of 100.
`chunk()` uses OFFSET — if you don't set an order, it auto-orders by primary key so
batches stay deterministic.

Return `False` from a `chunk`/`chunk_by_id`/`each` callback to stop early:

```python
async def handle_batch(batch: list[User]) -> bool:
    for user in batch:
        if await process(user) is None:
            return False  # stop iterating
    return True
```

Three streaming flavors:

```python
# Keyset paging — N LIMIT queries, stable under concurrent writes. Ascending by default.
async for user in User.lazy(500):
    ...
async for user in User.lazy_by_id(500, descending=True):  # high-to-low
    ...
await User.chunk_by_id(500, handle_batch, descending=True)

# Server-side cursor — one statement, rows pulled from the driver incrementally.
# Fires `retrieved` per row; does not batch-eager-load pivots.
async for user in User.stream(batch_size=500):
    ...
```

## CTEs (Common Table Expressions)

Pass any SQLAlchemy `CTE` object to `with_cte()`:

```python
from sqlalchemy import select, func

recent_orders_cte = (
    select(Order.__table__)
    .where(Order.created_at >= thirty_days_ago)
    .cte("recent_orders")
)

results = await (
    User.with_cte("recent_orders", recent_orders_cte)
    .join(recent_orders_cte, recent_orders_cte.c.user_id == User.id)
    .get()
)
```

## Recursive queries and tree assembly

For adjacency-list tables (any model with a `parent_id` column), chain `.recursive()` to get a `RecursiveQueryBuilder`:

```python
# Flat list of all descendants of node 5
descendants = await (
    Category.where(id=5)
    .recursive("parent_id")
    .all()
)
```

### Tree structure

`as_tree()` returns a nested `list[TreeNode[T]]` assembled in a single O(n) pass — no recursive round-trips to the database:

```python
from arvel.database import TreeNode

roots: list[TreeNode[Category]] = await (
    Category.recursive("parent_id", depth_col="depth")
    .as_tree()
)

def print_tree(nodes: list[TreeNode[Category]], indent: int = 0) -> None:
    for node in nodes:
        print(" " * indent, node.node.name, f"(depth={node.depth})")
        print_tree(node.children, indent + 2)

print_tree(roots)
```

Each `TreeNode[T]` carries:

| Attribute | Type | Description |
|---|---|---|
| `node` | `T` | The hydrated model instance |
| `depth` | `int` | Distance from the anchor row (0 = root) |
| `children` | `list[TreeNode[T]]` | Direct children, ordered by depth |

### Options

| Parameter | Default | Purpose |
|---|---|---|
| `parent_key` | (required) | Column that holds the parent FK |
| `id_key` | `"id"` | Column used as the PK/join key |
| `depth_col` | `None` | Adds a `_tree_depth` column to the CTE; required for `as_tree()` depth tracking |
| `path_col` | `None` | Reserved for materialised-path variants |

### Anchor filtering

Any `.where()` applied before `.recursive()` becomes the CTE anchor — it controls which rows are treated as roots:

```python
# Only the subtree rooted at category 5
tree = await (
    Category.where(id=5)
    .recursive("parent_id", depth_col="depth")
    .as_tree()
)
```

### Inspecting the SQL

```python
sql = (
    Category.where(parent_id=None)
    .recursive("parent_id", depth_col="depth")
    .to_sql()
)
print(sql)
# → WITH RECURSIVE categories_tree(id, parent_id, _tree_depth) AS (
#       SELECT id, parent_id, 0 AS _tree_depth FROM categories WHERE parent_id IS NULL
#       UNION ALL
#       SELECT c.id, c.parent_id, t._tree_depth + 1
#       FROM categories c JOIN categories_tree t ON c.parent_id = t.id
#   )
#   SELECT ...
```

## Inspecting the SQL

```python
qb = User.where(active=True).order_by("-created_at")
print(qb.to_sql())
# → "SELECT * FROM users WHERE active = $1 ORDER BY created_at DESC"
```

Useful for debugging and explaining queries. The parameters are kept separate, so this never leaks user data into the printed SQL.

## Full-text search (PostgreSQL)

Arvel ships thin helpers that sit directly on the query builder — no separate search index, no external dependency. They require a `tsvector` column (or a generated one) and are PostgreSQL-only.

### Basic search

```python
# Find posts whose search_vector matches the query
results = await (
    Post.where_full_text(Post.search_vector, "python async framework")
    .get()
)
```

`where_full_text` appends a `col @@ plainto_tsquery(lang, query)` clause. The query string is always a bind parameter — SQL injection is structurally impossible.

### Ranking results

```python
# Order by relevance (ts_rank DESC)
results = await (
    Post.where_full_text(Post.search_vector, "python async framework")
    .order_by_relevance(Post.search_vector, "python async framework")
    .limit(20)
    .get()
)
```

`order_by_relevance` appends `ORDER BY ts_rank(col, plainto_tsquery(lang, query)) DESC` as a new ordering clause.

### Choosing the tsquery function

Four PostgreSQL tsquery functions are supported:

```python
# plainto_tsquery (default) — simple word matching, ignores operators
Post.where_full_text(Post.search_vector, "async python")

# websearch_to_tsquery — interprets Google-style syntax ("async" OR python, -exclude)
Post.where_full_text(Post.search_vector, '"async python" OR framework', tsquery_fn="websearch_to_tsquery")

# to_tsquery — full tsquery syntax (requires the caller to add & / | operators)
Post.where_full_text(Post.search_vector, "python & (async | sync)", tsquery_fn="to_tsquery")

# phraseto_tsquery — phrase proximity match
Post.where_full_text(Post.search_vector, "async python framework", tsquery_fn="phraseto_tsquery")
```

Passing any other string raises `ValueError` immediately — before any SQL is built.

### Language

Both methods accept a `lang` keyword argument (default `"english"`):

```python
results = await Post.where_full_text(Post.search_vector, "python", lang="simple").get()
```

### Chaining

Both helpers return `Self` and chain naturally with the rest of the builder:

```python
results = await (
    Post.where(published=True)
    .where_full_text(Post.search_vector, "python framework")
    .order_by_relevance(Post.search_vector, "python framework")
    .limit(10)
    .get()
)
```

### Setting up the column and index

See [Migrations → Full-text search](migrations.md#full-text-search-postgresql) for how to add the `tsvector` column and GIN index to your table.

### QueryBuilder (non-model) usage

```python
# Against a raw table builder — pass the column attribute explicitly
from arvel.database import DB, Post

qb = DB.table("posts")
# ... not available on raw table builders; use the model classmethod form
# or build the clause manually with DB.raw()

# Model form (recommended):
ranked = await Post.where_full_text(Post.search_vector, "query").order_by_relevance(Post.search_vector, "query").get()
```

## Where to next?

- [Pagination](pagination.md) — paginating result sets.
- [Migrations](migrations.md) — managing your schema.
- [ORM](arvent.md) — when you want models, relationships, and lifecycle hooks.
