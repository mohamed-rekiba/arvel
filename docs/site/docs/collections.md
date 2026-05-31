# Collections

`Collection` is Arvel's fluent wrapper around `list[T]` — a typed, chainable container for working with sequences of items. It's what `Model.get()` and every Arvent query return.

## Creating collections

```python
from arvel.support import Collection


numbers = Collection([1, 2, 3, 4, 5])
users = Collection(await User.get())
```

`Collection[T]` is a `list[T]` subclass — anything that works on a list works on a collection, plus the additional fluent methods below.

## Transformations

```python
even_squared = (
    Collection([1, 2, 3, 4, 5])
    .filter(lambda n: n % 2 == 0)
    .map(lambda n: n * n)
    .all()
)
# → [4, 16]
```

Common methods:

| Method | Description |
|---|---|
| `.filter(fn)` | Keep items where `fn(item)` returns truthy |
| `.reject(fn)` | Drop items where `fn(item)` returns truthy |
| `.map(fn)` | Apply `fn` to each item, keeping the same length |
| `.flat_map(fn)` | `map`, then flatten one level |
| `.pluck(key)` | Extract `item[key]` (dicts) or `item.key` (objects) |
| `.where(key, value)` | Keep items where `item.key == value` |
| `.where_in(key, values)` | Keep items where `item.key in values` |
| `.unique(key=None)` | Deduplicate (optionally by key) |
| `.sort(key=..., reverse=...)` | Sort, returning a new collection |
| `.group_by(key)` | Group into a dict of collections |
| `.chunk(size)` | Split into smaller collections |

## Aggregations

```python
total = numbers.sum()
avg = numbers.avg()
max_value = numbers.max()
min_value = numbers.min()
count = numbers.count()
```

For computed aggregates, pass a key or callable:

```python
total_spent = orders.sum("total")
avg_age = users.avg(lambda u: u.age)
```

## Reductions

```python
combined = numbers.reduce(lambda carry, n: carry + n, 0)
```

For most cases, `.sum()`, `.avg()`, etc. cover what you need without writing reducers.

## Finding and set operations

```python
numbers = Collection([1, 2, 3, 4])

numbers.find(3)        # 3 — first item equal to the argument, or None
numbers.only(2, 4)     # Collection([2, 4]) — keep only the listed values
numbers.except_(2, 4)  # Collection([1, 3]) — drop the listed values
numbers.contains(3)    # True
```

`find`, `only`, and `except_` compare by value (`==`), so they work on unhashable members too. On a [ModelCollection](arvent-collections.md) these same methods key off the primary key instead — `posts.only(1, 3)` selects by id, not by equality.

## Lazy collections

For large datasets, use a `LazyCollection` to defer evaluation until you actually need values:

```python
from arvel.support import LazyCollection


users = await User.all()
big = LazyCollection(users)
adult_emails = big.filter(lambda u: u.age >= 18).map(lambda u: u.email)

for email in adult_emails:
    await send_email(email)
```

Lazy collections never materialize the full sequence; they pipe items through the transformations one at a time.

## When to use Collection vs list comprehension

Both are idiomatic Python.

Use a **list comprehension** for simple, one-step transforms:

```python
emails = [u.email for u in users if u.age >= 18]
```

Use a **Collection** when you're chaining multiple transforms or want the named methods to document intent:

```python
emails = (
    Collection(users)
    .where("active", True)
    .filter(lambda u: u.age >= 18)
    .pluck("email")
    .unique()
    .sort()
    .all()
)
```

Both produce the same output; pick what reads best for your team.

## Where to next?

- [ORM Collections](arvent-collections.md) — model-aware collections returned by queries.
- [Helpers](helpers.md) — string and array helpers.
