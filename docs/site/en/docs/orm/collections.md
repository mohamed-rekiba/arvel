# Collections

Query results do not have to stop at a plain Python `list`. `ArvelCollection` subclasses `list` and adds the chainable helpers Laravel developers know — map, filter, group, pluck — without giving up normal list behavior.

`QueryBuilder.all()` already returns `ArvelCollection` instances. When you are hand-building data, wrap iterables with `collect()`.

## Creating a collection

```python
from arvel.data.collection import collect, ArvelCollection

users: ArvelCollection[User] = await User.query(session).all()

tags = collect(["python", "arvel", "async"])
```

`collect()` accepts any iterable (or `None` for an empty collection) and preserves the element type for checkers.

## Transformation

`map` and `flat_map` return new collections; the originals stay untouched. `filter` and `reject` split rows without reaching for list comprehensions everywhere.

```python
names = users.map(lambda u: u.name.upper())
admins = users.filter(lambda u: u.role == "admin")
```

`each` runs a side-effect function over items and returns the same collection — handy for logging or dispatching events without breaking a fluent chain.

## Extraction

`pluck` pulls a single attribute or mapping key from each element. `first` and `last` accept an optional default when the collection is empty.

```python
ids = users.pluck("id")
owner = users.first_where("email", "owner@example.com")
```

## Grouping and chunking

`group_by` accepts either a string attribute name or a callable, returning a dict of `ArvelCollection` buckets. `chunk` splits into fixed-size batches — perfect for processing large sets without holding everything in memory twice.

## Ordering and uniqueness

`sort_by` sorts by key or callback. `unique` collapses duplicates. The methods mirror Laravel’s collection where it makes sense for Python, adapted to typing-friendly callables.

## JSON and interoperability

Collections behave like lists for `len`, slicing, truthiness, and iteration. When you need to serialize, the type cooperates with typical JSON encoders because it is still a sequence of your models or scalars.

Reach for `collect()` anytime a plain list feels too bare — especially at API boundaries where you want expressive manipulation without importing another dependency.
