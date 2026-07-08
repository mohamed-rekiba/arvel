# Queries

The query builder is how you read and write rows without hand-writing SQL. Every model exposes it
— `Post.where(...)`, `Post.find(...)`, `Post.create(...)` — and each method returns the builder
again, so you compose a query by chaining and only touch the database when you call a *terminal*
like `get()`, `first()`, or `count()`. Under the hood it compiles to SQLAlchemy Core, so the SQL
comes out dialect-correct across SQLite, MySQL, and Postgres; you stay in Python and the builder
handles the rest.

This page covers reading and writing rows, joins and grouped filters, walking large tables with
chunking and streaming, keyset pagination, and reusable scopes. Relation queries — eager loading
and aggregates over *related* rows — live in [Relationships](relationships.md).

## Querying

```python
posts = await Post.where(published=True).order_by("-created_at").limit(10).get()
one   = await Post.find(1)
first = await Post.where("views", ">", 100).first()
count = await Post.where(published=True).count()
page  = await Post.paginate(per_page=20)   # a LengthAwarePaginator — see Pagination
```

`paginate()` returns a [paginator](../pagination.md) (iterable over the page of rows, with
`total()`/`current_page()`/`last_page()` accessors, JSON shape, and `links()` HTML),
not a plain dict.

The builder carries the everyday query methods:

```python
await Post.where_in("status", ["draft", "review"]).get()
await Post.where_not_in("status", ["archived"]).get()
await Post.where_between("views", [100, 1000]).get()        # also where_not_between
await Post.when(tag, lambda q, value: q.where(tag=value)).get()  # conditional clause; the truthy
                                                                # value is passed
await Post.when(tag, lambda q: q.where(tag=tag)).get()      # 1-arg form (close over it) also works
await Post.unless(archived, lambda q: q.where("status", "!=", "archived")).get()  # inverse of when
await Post.order_by("views", "desc").skip(10).take(5).get() # skip/take alias offset/limit
await Post.where(published=True).pluck("title")             # ["Hello", …] (or pluck("title","id") → dict)
await Post.where(slug=s).value("title")                     # one column of the first row
await Post.find_or_fail(1)                                  # ModelNotFound on miss → HTTP 404
await Post.where(slug=s).first_or_fail()                    # same — no manual `if None: abort(404)`
```

`Model.all()`, `Model.query().get()`, and every relation `get()` return an
[**`ModelCollection`**](relationships.md#model-collection) — a model-aware, list-compatible
result set (`load`/`find`/`make_hidden`/`to_query`/…), not a plain `list`.


## Joins, having, and column/date comparisons

```python
await Post.query().join("users", "posts.user_id", "=", "users.id").select_raw("users.name").get()
await Post.query().left_join("comments", "posts.id", "=", "comments.post_id").get()
await Post.query().right_join("users", "posts.user_id", "=", "users.id").get()

await Post.where_column("updated_at", ">", "created_at").get()   # compare two columns
await Post.where_column("id", "author_id").get()                 # 2-arg form implies "="

await Post.where_date("published_at", "=", date(2026, 6, 1)).get()  # just the DATE portion
await Post.where_time("published_at", ">", time(9, 0)).get()
await Post.where_year("published_at", "=", 2026).get()
await Post.where_month("published_at", "=", 6).get()
await Post.where_day("published_at", "=", 1).get()

await Post.order_by_raw('FIELD(status, "draft", "published")').get()
```

`join`/`left_join`/`right_join` build a real SQLAlchemy Core `Table.join()` on the `FROM` clause
(not a raw string) — `right_join` is compiled as a swapped-side `left_join` since Core has no
`RIGHT JOIN` primitive. The default select stays `SELECT <this table>.*`; pull in a joined
column with `select_raw("other_table.col")`.

`having`/`having_raw` filter grouped rows (after `group_by`) — pair with `select_raw` for the
aggregate:

```python
stmt = (
    Sale.select_raw("region, sum(amount) AS total")
    .group_by("region")
    .having("total", ">", 1000)          # SQLite/MySQL accept the SELECT-list alias in HAVING
    .to_select()
)
rows = await app("db").fetch_all(stmt)
```

**Postgres divergence:** unlike SQLite/MySQL, Postgres rejects a SELECT-list alias in `HAVING`
(a SQL-standard restriction the `having()` hits too, not an arvel gap) — repeat the
aggregate expression with `having_raw("sum(amount) > ?", [1000])` instead.


## Chunking and streaming

```python
await Post.query().order_by("id").chunk(500, lambda rows: process(rows))     # offset-based
await Post.query().order_by("id").chunk_by_id(500, lambda rows: process(rows))  # keyset — stable under inserts
await Post.query().each(lambda post: process(post), chunk_size=500)          # one row at a time
async for post in Post.query().cursor():                                      # server-side cursor
    process(post)
```

`chunk`/`chunk_by_id`/`each` accept a sync or async callback; returning `False` stops the walk
early. Prefer `chunk_by_id`/`cursor` over `chunk` for a table with concurrent
writes — offset-based paging can skip/repeat rows as earlier pages shift.


## Cursor (keyset) pagination

```python
page = await Post.query().order_by("id").cursor_paginate(per_page=15)
page.data                          # not an attribute — use the accessors below
[p.title for p in page]            # iterable over the page's models
page.next_cursor()                 # an opaque base64 cursor, or None on the last page
page.previous_cursor()

next_page = await Post.query().order_by("id").cursor_paginate(
    per_page=15, cursor=page.next_cursor()
)
page.to_dict()  # {"data": [...], "path", "per_page", "next_cursor", "next_page_url", "prev_cursor", "prev_page_url"}
```

Unlike `paginate()`/`simple_paginate()` (offset-based — `OFFSET n LIMIT m`), `cursor_paginate`
seeks past the last row's ordering values, so pages stay correct even when rows are inserted
before the cursor mid-scan — the "page drift" `OFFSET` can't avoid. It requires an `order_by`
(defaults to the primary key ascending); the primary key is always appended as an implicit
tiebreaker when the given ordering isn't already unique, so paging is gap/dup-free even over a
non-unique column.


## Inserts, updates, deletes

```python
post = await Post.create(title="Hello", body="…")     # mass-assignment guarded by __fillable__
post.title = "Edited"
await post.save()                                      # only when dirty
await post.delete()

await Post.where(draft=True).update({"published": True})
user = await User.first_or_create({"email": e}, {"name": n})
```

`upsert(rows, unique_by, update=None)` inserts, updating `update` columns (defaults to every
non-key column) on a conflict over `unique_by`:

```python
await Product.upsert(
    [{"sku": "A", "price": 10}, {"sku": "B", "price": 20}], ["sku"], ["price"]
)
```

Dialect-correct: Postgres/SQLite compile `ON CONFLICT ... DO UPDATE`; MySQL/MariaDB compile
`ON DUPLICATE KEY UPDATE` (`unique_by` is honored by documentation only there — MySQL has no
`ON CONFLICT(cols)` targeting, matching, which ignores `$uniqueBy` on MySQL too). An
unrecognized dialect raises `UnsupportedDriverOperation` rather than silently emitting the wrong
SQL.


## Scopes

Reusable query constraints. A **local** scope is a `scope_*` method callable as a query method;
a **global** scope applies to every query for the model:

```python
class Post(Model):
    def scope_published(self, query):         query.where(published=True)
    def scope_authored_by(self, query, user): query.where(user_id=user.id)

await Post.published().authored_by(ada).get()

Post.add_global_scope("not_archived", lambda q: q.where_null("archived_at"))
await Post.get()                              # archived rows excluded automatically
await Post.without_global_scope("not_archived").get()
```

Prefer to name the method after the scope itself? Decorate it with `@scope` instead of using the
`scope_` prefix — the method name *is* the query method:

```python
from arvel import scope

class Post(Model):
    @scope
    def published(self, query):         query.where(published=True)
    @scope
    def authored_by(self, query, user): query.where(user_id=user.id)

await Post.published().authored_by(ada).get()   # identical call site
```

Both styles are equivalent and may be mixed on the same model; `@scope` just frees the name from
the prefix.

## How it works

Every builder method records a clause and returns the same `Builder` — nothing hits the database
until a *terminal* runs (`get`/`first`/`count`/`paginate`/`chunk`/`cursor`/…). At that point the
builder assembles a SQLAlchemy Core statement and hands it to the connection, which is why the SQL
is dialect-correct: the `upsert` and `having` divergences above are the builder compiling the right
statement per driver, not leaking the difference up to you. On the way back, `get()` hydrates each
row into a model through the model's `_hydrate` and wraps them in a
[`ModelCollection`](relationships.md#model-collection); a raw table builder with no model bound
skips hydration and returns plain `dict` rows instead.

## Common mistakes & gotchas

- **`get()` when you meant `first()`.** `get()` always returns a list (empty if nothing matched);
  `first()` returns one model or `None`, and `find(id)` looks up by primary key. Reaching for
  `[0]` on a `get()` is a sign you wanted `first()`.
- **A silent global scope.** A registered global scope filters *every* query on the model — if a
  count looks wrong, check for one and use `without_global_scope(name)` when you need the raw set.
- **N+1 in a loop.** Iterating models and touching a relation per row fires a query each time; batch
  it with `with_(...)` — see [Relationships](relationships.md).
- **`where("col", value)` vs `where("col", ">", value)`.** Two args is an equality check; an operator
  needs the three-arg form.

## See also

- [Relationships](relationships.md) — relation queries, eager loading, and aggregates.
- [Transactions & Streaming](transactions.md) — locking, and streaming large result sets.
- [Pagination](../pagination.md) — `paginate()`/`simple_paginate()` on any query chain.
- [Casts & Serialization](casts.md) — how the rows a query returns map to Python types.
