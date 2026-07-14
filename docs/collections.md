# Collections

`Collection` is a fluent, chainable wrapper around a list of items. It provides dozens of methods for
mapping, filtering, reducing, and reshaping data — a far more expressive alternative to threading a
list through nested comprehensions.

## Introduction

Wrap any iterable with the `collect()` helper:

```python
from arvel.support import collect

names = (
    collect([{"name": "Ada"}, {"name": "Grace"}, {"name": "Linus"}])
    .pluck("name")            # Collection(["Ada", "Grace", "Linus"])
    .map(str.upper)           # Collection(["ADA", "GRACE", "LINUS"])
    .sort()
    .all()                    # ["ADA", "GRACE", "LINUS"]
)
```

Almost every method returns a **new** `Collection`, so calls chain without mutating the source.
`.all()` (or `.to_list()`) unwraps back to a plain list.

## Available methods

### Transforming

```python
collect(items).map(fn)                 # transform each item
collect(items).filter(fn)              # keep items where fn is truthy
collect(items).reject(fn)              # drop items where fn is truthy
collect(items).reduce(fn, initial)     # fold to a single value
collect(items).each(fn)                # side effect per item (returns self)
collect(items).flatten()               # flatten one level of nesting
collect(items).chunk(3)                # Collection of size-3 lists
```

### Querying

```python
collect(users).where("active", True)         # rows matching a key/value
collect(users).where_in("role", ["a", "b"])
collect(users).where_null("deleted_at")
collect(users).first_where("email", "a@b.c")
collect(users).pluck("email")                # extract one key
collect(users).contains(item)                # membership (or predicate)
collect(users).sole(lambda u: u.admin)       # the one match, or raise
```

### Aggregating

```python
collect(nums).sum()              # or .sum("price") over dicts/objects
collect(nums).avg()              # also .median() / .mode()
collect(nums).min()              # and .max()
collect(users).count()
collect(users).count_by("role")  # {"admin": 2, "user": 9}
collect(users).group_by("team")  # {"blue": [...], "red": [...]}
collect(users).key_by("id")      # {1: {...}, 2: {...}}
```

### Ordering & slicing

```python
collect(items).sort()                    # natural order
collect(items).sort_by("age")            # by a key (sort_by_desc for reverse)
collect(items).unique()
collect(items).reverse()
collect(items).take(3)                   # first 3 (negative = last 3)
collect(items).skip(2).slice(0, 5)
collect(items).nth(2)                    # every 2nd item
collect(items).shuffle() / .random()
```

### Partitioning & testing

```python
active, inactive = collect(users).partition(lambda u: u.active)
collect(users).every(lambda u: u.active)   # all match?
collect(users).is_empty()
```

## Lazy collections

A `Collection` is eager — each step builds a new list. For a **large or streaming** source (a big
file, a generator, a paginated API) where you don't want the whole thing in memory, use a
`LazyCollection`: it chains `map`/`filter`/`each`/`take` as generators and only pulls items as the
final step consumes them. Start one from a generator/iterable directly, or `.lazy()` off a
Collection:

```python
from arvel.support import LazyCollection

def read_rows():                       # a generator — nothing loaded yet
    with open("huge.csv") as f:
        yield from f

first_ten_active = (
    LazyCollection(read_rows)
    .map(parse)
    .filter(lambda r: r.active)
    .take(10)                          # stops reading the file after 10 matches
    .to_list()
)

collect(items).lazy().filter(...).first()   # or drop into lazy mode from a Collection
```

`take`/`first` **short-circuit** — they stop consuming the source as soon as they have enough, so an
infinite or huge source is fine. Call `.collect()` (or `.to_list()`) to materialize back into an
eager `Collection`/list once the set is small.

## See also

- [Strings](strings.md) — the same fluent style over a single string.
- [ORM: Collections](database/collections.md) — query results returned as collections of models.
