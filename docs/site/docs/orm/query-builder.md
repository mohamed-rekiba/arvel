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
names = await Item.query().pluck("name")
```

<a name="aggregates"></a>
### Aggregates

```python
total = await Item.where(is_active=True).count()
revenue = await Item.query().sum("price")     # empty result → 0
top = await Item.query().max("price")
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
| `where_date` / `where_year` / `where_month` / `where_day` | date-part filters |
| `where_column` | compare two columns |
| `where_raw` | `where_raw("price > tax * 10")` |
| `where_exists` | correlated `EXISTS` subquery |
| `where_json_path` / `where_json_contains` | PostgreSQL JSON filters |
| `where_full_text` | full-text search |
| `where_any` / `where_all` / `where_none` | apply an operator across several columns |
| `has` / `where_has` / `doesnt_have` / `where_relation` | filter by [related rows](relationships.md#querying-relationship-existence) |

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

<a name="conditional-clauses"></a>
## Conditional Clauses

Build queries from runtime conditions without breaking the chain. `when` runs the callback when the condition is truthy; `unless` runs it when falsy:

```python
query = Item.query()
query = query.when(search, lambda q: q.where_like("name", f"%{search}%"))
query = query.unless(include_inactive, lambda q: q.where(is_active=True))
items = await query.get()
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
page = await Item.query().simple_paginate(per_page=15)
page.has_more

# keyset cursor pagination — best for deep, stable scrolling
page = await Item.query().cursor_paginate(per_page=15, cursor=token)
page.next_cursor
page.prev_cursor
```

A cursor token is opaque — clients pass back whatever `next_cursor`/`prev_cursor` gave them. If a request arrives with a hand-edited or truncated `?cursor=`, decoding raises `InvalidCursorError`. The default HTTP wiring translates that to a `400 Bad Request` with a fixed message, so a malformed cursor never surfaces as a `500` or leaks the base64/JSON decode internals.

<a name="chunking-and-streaming"></a>
## Chunking & Streaming

To process large result sets without loading everything into memory:

```python
# iterate one row at a time
async for item in Item.query().lazy():
    ...

# process in batches; return False from the callback to stop early
await Item.query().chunk(500, process_batch)

# stable when the callback mutates rows that would shift offsets
await Item.query().chunk_by_id(500, process_batch)
```

<a name="bulk-writes"></a>
## Bulk Writes

The builder runs set-based writes that bypass per-row model events:

```python
await Item.where(is_active=False).update({"is_active": True})
await Item.query().insert([{...}, {...}])
new_id = await Item.query().insert_get_id({...})
await Item.query().upsert(rows, unique_by=["sku"], update=["price"])
await Item.where(...).increment("views")
await Item.where(...).decrement("stock", 2)
await Item.where(...).delete()        # soft delete if SoftDeletes, else hard
```

Get-or-create helpers cover the common idioms: `first_or_create`, `first_or_new`, `update_or_create`, `update_or_insert`.

> [!WARNING]
> Bulk writes operate at the SQL level and do **not** fire [model events](models.md#model-events) or run per-row casts. When you need events, load the models and save them individually.

<a name="scopes"></a>
## Scopes

<a name="local-scopes"></a>
### Local Scopes

Local scopes are reusable query fragments. Define a `scope_<name>` method on the model and call it as `Model.<name>()`:

```python
class Post(Model, Timestamps):
    __tablename__ = "posts"
    id: int = id_()

    def scope_published(self, query):
        return query.where(status="published")

    def scope_of_author(self, query, author_id: int):
        return query.where(user_id=author_id)


published = await Post.published().get()
mine = await Post.published().of_author(7).get()
```

<a name="global-scopes"></a>
### Global Scopes

Global scopes apply to every query for a model — this is exactly how soft deletes hide trashed rows. Register one and opt out per query:

```python
Post.add_global_scope("tenant", lambda q: q.where(tenant_id=current_tenant()))

await Post.query().without_global_scope("tenant").get()
await Post.query().without_global_scopes().get()
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
