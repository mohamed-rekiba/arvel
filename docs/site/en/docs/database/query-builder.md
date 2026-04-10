# Query Builder

The query builder is where Arvel feels closest to Laravel’s Eloquent, but with SQLAlchemy 2.0 under the hood. You chain fluent methods, every predicate is a real `ColumnElement` — so parameters are bound safely, and your editor still knows the types.

You usually start from a model: `User.query(session)` returns a `QueryBuilder[User]`. From there you filter, order, eager-load, and aggregate without writing raw SQL strings.

## Building a query

The heart of the builder is a `select()` over your mapped class. Methods return `self`, so you compose in the order that reads naturally.

```python
from sqlalchemy import func

users = await (
    User.query(session)
    .where(User.is_active == True)
    .order_by(User.name)
    .limit(20)
    .all()
)
```

`where()` accepts multiple criteria; they are combined with AND. Use SQLAlchemy expressions (`User.role.in_(("admin", "editor"))`, `User.created_at >= start`) rather than string fragments.

## Ordering and pagination

`order_by()` maps straight to SQLAlchemy. Call it before `first()` — the builder warns if you ask for `first()` without ordering, because the database is otherwise free to pick any row.

`limit()` and `offset()` do exactly what you expect and pair naturally with offset-style pagination. For large tables, consider cursor-based patterns (see the Pagination page) instead of huge offsets.

## Eager loading

Async code and implicit lazy loading do not mix well. Arvel defaults to strict relationship loading in many setups, so you opt in to related data with `with_()`, which uses `selectinload` and supports dotted paths.

```python
posts = await (
    Post.query(session)
    .with_("author", "comments", "comments.author")
    .where(Post.published_at.isnot(None))
    .all()
)
```

## Relationship filters

Sometimes you need rows of `User` based on conditions on `Post`. Use `has()`, `doesnt_have()`, or `where_has()`:

```python
# Users with at least one post
await User.query(session).has("posts").all()

# Users with more than five posts
await User.query(session).has("posts", ">", 5).all()

# Users who have published posts
await User.query(session).where_has(
    "posts",
    lambda Post: Post.is_published == True,
).all()
```

`where_has()` receives the **related model class** in the lambda and must return a boolean SQL expression.

## Aggregates and counts

`count()` runs a COUNT over the current constrained query. For `max`, `min`, `sum`, and friends, the builder exposes aggregate helpers that operate on a subquery derived from your filters — so you stay in fluent API land.

```python
total = await User.query(session).where(User.is_active == True).count()
```

## Subqueries and relationship counts

`with_count()` adds correlated subqueries for relationship counts, which is perfect for list screens that show "number of comments" without N+1 queries. Pair the query with `all_with_counts()` to receive `WithCount` wrappers that bundle the model and a `counts` dict.

```python
rows = await User.query(session).with_count("posts").all_with_counts()
for row in rows:
    print(row.instance.name, row.counts["posts"])
```

## Recursive trees

Hierarchical data gets first-class support: `recursive()`, `ancestors()`, and `descendants()` build `WITH RECURSIVE` CTEs for self-referential tables. That is a bigger topic, but it lives on the same builder — you are never pushed down to raw SQL unless you choose to.

## Debugging SQL

When you truly need the string, `to_sql()` compiles the statement — but only when `ARVEL_DEBUG` is enabled, so production logs do not accidentally fill with giant queries.

The query builder is your everyday interface to the database: expressive like a Laravel model, transparent like SQLAlchemy, and async from the first call to the last.
