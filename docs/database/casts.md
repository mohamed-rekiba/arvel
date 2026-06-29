# Casts & Serialization

## Casts & change tracking

```python
post.was_changed("title")        # since the last save
post.get_original("title")
fresh = await post.fresh()       # re-fetch from the database
```

Casts include `datetime`, `bool`, `int`, `json`, native `enum`, and (via the container)
`encrypted` and `hashed`.

### Dates & timestamps

A `datetime` cast (and `created_at`/`updated_at`/`deleted_at`, plus any field declared with a
`datetime` type) is stored in the database as a **real timezone-aware `DateTime`** column and reads
back as an arvel [`Date`](../dates.md) — not an ISO string. This means a timestamped model persists
correctly on PostgreSQL `timestamp with time zone` columns, not just SQLite.

```python
class Post(Model):
    __fields__ = {"title": str, "published_at": datetime}   # real DateTime column
    __casts__ = {"published_at": "datetime"}                # (optional — a datetime field auto-casts)
    __timestamps__ = True

post = await Post.create(title="Hi", published_at=Date.now())
post.published_at          # -> a Date (e.g. post.published_at.diff_for_humans())
post.created_at            # -> a Date, not a string
```

You can set a datetime column from a `Date`, a stdlib `datetime`, or an ISO-8601 string — all are
normalized to a real datetime on write. In JSON responses a `Date` is serialized to an ISO-8601 string
automatically.

Serialize with `to_dict()` (honors `__hidden__`/`__visible__`/`__appends__`) or `to_json()`
for a JSON string of the same shape — `Date`, `Decimal`, and `Enum` values are encoded for you:

```python
post.to_dict()                   # {"title": ..., "slug": ...}  — hidden keys dropped
post.to_json()                   # '{"title": ..., "slug": ...}'
```
