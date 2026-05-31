# Mutators / Casts

Casts let you transform attribute values as they go in and out of the database. Common cases:

- Storing JSON as a `dict` in code, JSON in the column.
- Storing an enum as a string in the column.
- Storing an encrypted column without the application code having to think about crypto.
- Storing a Pydantic model as JSON.

Two flavours: column-level (e.g. `EnumType`, `PydanticType`, `EncryptedType`) round-trip the value through SQL and the result row, and attribute-level
(`__casts__`) coerces values on Python reads only. Pick the column-level type when SQL needs the typed value too; reach for `__casts__` when the column
already holds the right SQL shape and you just want a cleaner Python view.

## Built-in casts

### Enum

```python
from enum import StrEnum
from arvel.database import EnumType, column


class Status(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"


class Post(Model):
    status: Status = column(EnumType(Status), default=Status.DRAFT)
```

`Post.status` is a `Status` value in Python, stored as the string `"draft"` or `"published"` in the database.

### Pydantic models

```python
from pydantic import BaseModel
from arvel.database import PydanticType, column


class Settings(BaseModel):
    theme: str = "light"
    notifications: bool = True


class User(Model):
    settings: Settings = column(PydanticType(Settings))
```

`User.settings` is a `Settings` instance in Python, stored as a JSON column in the database.

### Encrypted

```python
from arvel.database import EncryptedType, column


class User(Model):
    secret: str = column(EncryptedType(key_b64=os.environ["APP_KEY"]))
```

AES-GCM authenticated encryption, transparent to your application code. See [Encryption](encryption.md) and ADR-014 for details.

For searchable encryption (deterministic IV, equal plaintext → equal ciphertext):

```python
secret: str = column(EncryptedType(key_b64=..., mode="search"))
```

### JSON

Plain JSON without Pydantic validation:

```python
from arvel.database import json


class User(Model):
    metadata: dict = json()
```

For the strict + typed version, prefer `PydanticType` with a model.

### Hashed

For columns that store a digest (not encryption — see [Hashing](hashing.md)):

```python
from arvel.database import HashedType, column


class Token(Model):
    value: str = column(HashedType("sha256"))
```

Writing `token.value = "secret"` stores the SHA-256 hex. The plaintext is never written to the column. Useful for API key storage (ADR-030).

## Lightweight attribute casts (`__casts__`)

For value-level coercion that doesn't need a custom SQLAlchemy type — like
"this `score` column is stored as a string but I want an int in Python", or
"this `published_at` is an ISO timestamp string in the DB but I want a
`datetime` in code" — set `__casts__` on the model. Each entry maps a column
name to a cast type name.

```python
from arvel.database import Model, integer, string


class Post(Model):
    __tablename__ = "posts"
    __casts__ = {
        "published": "boolean",
        "view_count": "integer",
        "meta": "dict",
        "published_at": "datetime",
        "expires_on": "date",
        "queued_at": "timestamp",
    }
    published: int = integer(default=0)
    view_count: str = string(20, default="0")
    meta: str = string(500, default="{}")
    published_at: str = string(40, default=None)
    expires_on: str = string(10, default=None)
    queued_at: int = integer(default=0)
```

Reading any of these attributes runs the value through the cast on the way
out. **Assignment and construction run the same cast on the way in** for
scalar types (`boolean`, `integer`, `float`, `string`, and the temporal
trio). `None` bypasses the cast. Invalid values raise `CastError`
immediately at write time, not on the first read.

JSON collection casts (`dict`, `list`, `array`) stay **read-path only** on
write — coercing to a Python collection in memory would break `String`
column INSERTs. Assign the JSON string (or use a [TypeDecorator](#writing-custom-casts)
for column-level JSON).

Invalid cast names raise `ValueError` at class-definition time — typos
fail fast.

### Built-in cast types

| Cast name(s) | Returns | Accepts |
|---|---|---|
| `boolean`, `bool` | `bool` | matches PHP `(bool)`: `"0"` and `""` are `False`, every other non-empty string (including `"false"`) is `True` |
| `integer`, `int` | `int` | `int`, `str` that `int()` accepts |
| `float` | `float` | `int`, `float`, `str` that `float()` accepts |
| `string`, `str` | `str` | anything (`str()` coerces) |
| `dict`, `list`, `array` | `dict` / `list` | JSON string or pre-parsed value |
| `datetime` | tz-aware `datetime` (UTC) | ISO-8601 string, epoch seconds (int/float), `datetime` |
| `date` | `date` | ISO `YYYY-MM-DD`, ISO datetime, `datetime`/`date`, epoch seconds |
| `timestamp` | `int` (epoch seconds, UTC) | ISO-8601 string, `datetime`, epoch seconds |
| `decimal:n` | `Decimal` quantized to `n` places | `Decimal`, `int`, `float`, numeric string |
| `datetime:FMT` | tz-aware `datetime`; serializes via `strftime(FMT)` | string in `FMT`, ISO-8601 fallback, `datetime`, epoch |
| `object` | `SimpleNamespace` (attribute access); serializes to `dict` | JSON object string or pre-parsed value |
| `collection` | Arvel `Collection`; serializes to `list` | JSON array string or pre-parsed list |
| an `Enum` subclass | the enum member; serializes to its backing value | backing value or member |

The temporal trio (`datetime`, `date`, `timestamp`) normalises to UTC. A
naive `datetime` is *assumed* to be UTC — there's no implicit local-time
guesswork. A bad input (unparseable string, wrong type) raises `CastError`
(an `ORMError` subclass), so handlers can choose between 400 and 500
responses via the [HTTP exception translator](errors.md#orm-errors-http-envelope)
registry.

```python
post = await Post.find(1)
post.published_at      # datetime(2026, 5, 25, 1, 30, 0, tzinfo=UTC)
post.expires_on        # date(2026, 12, 31)
post.queued_at         # 1779672600
```

For column-level coercion that should also affect SQL operations (sorting,
filtering, indexing), prefer the [TypeDecorator](#writing-custom-casts) approach
below — `__casts__` runs on Python attribute reads and writes, but the
underlying column type is unchanged in SQL.

### Enums and extended built-ins

Pass an `Enum` subclass straight into `__casts__` — reads give you the member,
writes store the backing value, and `to_dict()` serializes back to the backing
value. A raw backing value assigned to the attribute coerces to the member too.

```python
from enum import Enum


class Status(Enum):
    DRAFT = "draft"
    PUBLISHED = "published"


class Article(Model):
    __tablename__ = "articles"
    __casts__ = {
        "status": Status,                       # enum member <-> backing value
        "meta": "object",                       # JSON -> SimpleNamespace
        "tags": "collection",                   # JSON -> Collection
        "scheduled_at": "datetime:%Y-%m-%d %H:%M",
    }
    status: str = string(40, default=None)
    meta: str = string(255, default="{}")
    tags: str = string(255, default="[]")
    scheduled_at: str = string(40, default=None)


a = Article(status="published")
a.status                    # Status.PUBLISHED
a.meta.author               # attribute access on the decoded object
list(a.tags)                # Collection, iterable like a list
a.to_dict()["scheduled_at"] # "2026-05-30 14:45"
```

`object` and `collection` are **read-path only** on write (like `dict`/`list`)
— assign the JSON string. `datetime:FORMAT` parses your format first and falls
back to ISO-8601, then serializes with `strftime`.

### Encrypted casts

Store a column encrypted at rest and work with the plaintext in code. The cast
encrypts on write and decrypts on read via the `Crypt` facade, which derives an
AES-256-GCM key from `APP_KEY`.

```python
class Account(Model):
    __tablename__ = "accounts"
    __casts__ = {
        "ssn": "encrypted",            # plaintext string
        "recovery_codes": "encrypted:array",
        "profile": "encrypted:object",      # -> SimpleNamespace
        "labels": "encrypted:collection",   # -> Collection
    }
    __hidden__ = ["ssn"]               # keep it out of to_dict()
    ssn: str = string(512, default=None)
    recovery_codes: str = string(512, default=None)
```

The stored column value is ciphertext; the attribute and `to_dict()` expose the
decrypted value (Eloquent `toArray` parity — pair it with `__hidden__` when the
plaintext shouldn't leave the server). Each write uses a fresh IV, so equal
plaintexts produce different ciphertext and the column isn't searchable by
equality. `APP_KEY` must be set (run `arvel key:generate`); a wrong key raises
`DecryptionError` on read.

## Accessors and mutators

For computed attributes that don't map to a single column, define a property:

```python
class User(Model):
    first_name: Mapped[str]
    last_name: Mapped[str]

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"
```

For "write to a virtual column, set multiple underlying columns" behavior, use a setter:

```python
class User(Model):
    @full_name.setter
    def full_name(self, value: str) -> None:
        self.first_name, _, self.last_name = value.partition(" ")
```

This is plain Python — Arvel doesn't add anything to it. The simplicity is the point.

### Unified `Attribute` (one name, get + set)

When a virtual attribute reads from and writes to several columns under one name,
`Attribute` keeps both halves together instead of a `@property` plus a separate
setter. `get` takes the model; `set` takes `(model, value)` and returns a mapping
of real columns to write.

```python
from arvel.database import Attribute, Model


class User(Model):
    first_name: str = string(50)
    last_name: str = string(50)

    full_name = Attribute.make(
        get=lambda m: f"{m.first_name} {m.last_name}".strip(),
        set=lambda m, v: dict(zip(("first_name", "last_name"), v.split(" ", 1))),
    )
```

`u.full_name` computes from the columns; `u.full_name = "Grace Hopper"` writes both
back through the normal cast/mutator path. A `get`-only `Attribute` is read-only; a
`set`-only one is write-only. Add `.should_cache()` to memoize the computed value per
instance — it's invalidated when you write through the attribute, but not when you
mutate a backing column directly, so reach for it only when that's fine.

## Default values

```python
class Post(Model):
    published: bool = boolean(default=False)
    # mapped_column here only because the datetime() helper name-clashes with the type.
    created_at: datetime = mapped_column(default=lambda: datetime.now(UTC))
```

For dynamic defaults (timestamps, UUIDs), pass a callable. The framework provides shortcuts:

```python
import uuid

from arvel.database import Timestamps, uuid_id


class Post(Model, Timestamps):
    id: uuid.UUID = uuid_id()
```

`Timestamps` adds `created_at` / `updated_at` and manages them on save. `uuid_id()` gives a UUIDv7 (time-ordered) primary key, generated per row.

## Writing custom casts

Implement `TypeDecorator` from SQLAlchemy:

```python
from sqlalchemy.types import TypeDecorator, String


class UpperString(TypeDecorator):
    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return value.upper() if value else value

    def process_result_value(self, value, dialect):
        return value
```

```python
from arvel.database import column


class User(Model):
    country_code: str = column(UpperString(2))
```

Now `user.country_code = "us"` stores `"US"`. `column()` is the generic helper for any custom `TypeDecorator` — same kwargs (`nullable`, `unique`, `index`, `default`) and `Mapped[T]` typing as the named helpers, so you never reach for `mapped_column` just to attach a custom type.

## Where to next?

- [ORM Getting Started](index.md) — defining models.
- [Encryption](encryption.md) — the crypto behind `EncryptedType`.
- [Validation](validation.md) — Pydantic patterns used by `PydanticType`.
