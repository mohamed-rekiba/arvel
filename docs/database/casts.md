# Casts & Serialization

## Casts & change tracking

```python
post.was_changed("title")        # since the last save
post.get_original("title")
fresh = await post.fresh()       # re-fetch from the database
```

Casts include `datetime`, `bool`, `int`, `json`/`array`, `collection`, `object`, `decimal:<scale>`,
native `enum`, `stringable`, and (via the container) `encrypted`/`encrypted:array`/`encrypted:json`
and `hashed`.

### The full cast set

```python
from decimal import Decimal

class Order(Model):
    __fields__ = {
        "items": list, "meta": dict, "settings": dict,
        "total": str, "notes": str, "reference": str,
    }
    __casts__ = {
        "items": "array",              # JSON column <-> list
        "meta": "json",                # JSON column <-> dict (alias of "array")
        "settings": "collection",      # JSON column <-> arvel.support.Collection
        "total": "decimal:2",          # <-> decimal.Decimal, quantized to 2 places on set
        "notes": "encrypted:array",    # ciphertext at rest, list/dict in Python
        "reference": "stringable",     # <-> arvel.support.Stringable
    }
```

- **`array`/`json`** — a JSON column stored as `TEXT` (the cast owns (de)serialization), read back
  as a `dict`/`list`. `array` and `json` are the same cast under two names.
- **`collection`** — like `array`, but reads back as an `arvel.support.Collection` instead of a
  plain `list`; writing accepts a `Collection` or any iterable.
- **`object`** — reads back as a `types.SimpleNamespace` (dotted access: `order.settings.theme`);
  writing accepts a `SimpleNamespace` or a plain `dict` (serialized via `vars()`).
- **`decimal:<scale>`** — a `decimal.Decimal`, quantized to `<scale>` places on write (and
  re-quantized on read). **Idiomatic divergence:** the `decimal` cast returns a *formatted
  string*; arvel returns a real `Decimal` so arithmetic doesn't round-trip through string parsing.
- **`encrypted:array`/`encrypted:json`** — like `encrypted`, but serialize-aware: the plaintext
  is a `dict`/`list`, not just a string.
  Ciphertext at rest, plaintext in Python — needs `encrypter` bound in the container (same as
  `encrypted`).
- **`stringable`** — reads back as an `arvel.support.Stringable` (a fluent string wrapper); writing
  accepts a `Stringable` or a plain `str`.
- **Not added: `immutable_datetime`.** arvel's `datetime` cast already returns the immutable,
  `whenever`-based [`Date`](../dates.md) — there's no separate mutable-vs-immutable cast to choose
  between, unlike (whose default `datetime` cast is mutable Carbon).

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
