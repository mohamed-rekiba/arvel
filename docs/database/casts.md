# Casts & Serialization

A database column has a database type — `TEXT`, `INTEGER`, `TIMESTAMP` — but that's rarely the type
you want to work with in Python. A `casts` declaration bridges the two: it says "this column is stored
as JSON but I want a `dict`", or "this is stored as text but I want a `Decimal`", and the model does
the conversion for you on every read and write. Alongside casts, a model tracks what changed since it
was loaded, and knows how to serialize itself to a plain dict or JSON for an API response — the two
things you reach for constantly once a model leaves the database.

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
- **`decimal:<scale>`** — a real `decimal.Decimal`, quantized to `<scale>` places on write (and
  re-quantized on read). You get a `Decimal`, not a formatted string, so arithmetic on a money column
  doesn't round-trip through string parsing.
- **`encrypted:array`/`encrypted:json`** — like `encrypted`, but serialize-aware: the plaintext
  is a `dict`/`list`, not just a string.
  Ciphertext at rest, plaintext in Python — needs `encrypter` bound in the container (same as
  `encrypted`).
- **`stringable`** — reads back as an `arvel.support.Stringable` (a fluent string wrapper); writing
  accepts a `Stringable` or a plain `str`.
- **No separate `immutable_datetime`.** arvel's `datetime` cast already returns the immutable,
  `whenever`-based [`Date`](../dates.md), so there's no mutable-vs-immutable distinction to pick
  between — every datetime you read back is immutable by default.

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

For richer, versioned API output — renamed fields, conditional inclusion, wrapping — reach for a
[JsonResource](resources.md) instead of hand-shaping `to_dict()`.

## Common mistakes & gotchas

- **Declaring a cast without a column to back it.** A `json`/`array` cast needs a column that can hold
  serialized text; pair the cast with a matching `__fields__` entry so the migration creates the right
  column type.
- **Expecting a mutable datetime.** Reads come back as an immutable [`Date`](../dates.md) — a
  `post.published_at.add(days=1)` returns a *new* `Date`, it doesn't mutate in place.
- **`encrypted` casts without an encrypter.** `encrypted`/`encrypted:json`/`encrypted:array` and
  `hashed` resolve their engine from the container — they raise if nothing is bound. See
  [Encryption](../encryption.md) and [Hashing](../hashing.md).
- **Comparing a `decimal` cast to a `float`.** The cast gives you a `Decimal`; compare and compute
  with `Decimal` values (or use the [Money](../money.md) type) rather than mixing in floats.

## See also

- [Migrations & Schema](migrations.md) — the column types a cast reads and writes.
- [API Resources](resources.md) — structured serialization beyond `to_dict()`.
- [Dates & Time](../dates.md) — the `Date` type the `datetime` cast returns.
- [Encryption](../encryption.md) · [Hashing](../hashing.md) — the engines behind `encrypted`/`hashed`.
