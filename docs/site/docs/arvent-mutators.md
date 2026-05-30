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
from arvel.database import EnumType


class Status(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"


class Post(Model):
    status: Mapped[Status] = mapped_column(EnumType(Status), default=Status.DRAFT)
```

`Post.status` is a `Status` value in Python, stored as the string `"draft"` or `"published"` in the database.

### Pydantic models

```python
from pydantic import BaseModel
from arvel.database import PydanticType


class Settings(BaseModel):
    theme: str = "light"
    notifications: bool = True


class User(Model):
    settings: Mapped[Settings] = mapped_column(PydanticType(Settings))
```

`User.settings` is a `Settings` instance in Python, stored as a JSON column in the database.

### Encrypted

```python
from arvel.database import EncryptedType


class User(Model):
    secret: Mapped[str] = mapped_column(EncryptedType(key_b64=os.environ["APP_KEY"]))
```

AES-GCM authenticated encryption, transparent to your application code. See [Encryption](encryption.md) and ADR-014 for details.

For searchable encryption (deterministic IV, equal plaintext → equal ciphertext):

```python
secret: Mapped[str] = mapped_column(EncryptedType(key_b64=..., mode="search"))
```

### JSON

Plain JSON without Pydantic validation:

```python
from sqlalchemy import JSON


class User(Model):
    metadata: Mapped[dict] = mapped_column(JSON)
```

For the strict + typed version, prefer `PydanticType` with a model.

### Hashed

For columns that store a digest (not encryption — see [Hashing](hashing.md)):

```python
from arvel.database import HashedType


class Token(Model):
    value: Mapped[str] = mapped_column(HashedType("sha256"))
```

Writing `token.value = "secret"` stores the SHA-256 hex. The plaintext is never written to the column. Useful for API key storage (ADR-030).

## Lightweight attribute casts (`__casts__`)

For value-level coercion that doesn't need a custom SQLAlchemy type — like
"this `score` column is stored as a string but I want an int in Python", or
"this `published_at` is an ISO timestamp string in the DB but I want a
`datetime` in code" — set `__casts__` on the model. Each entry maps a column
name to a cast type name.

```python
from arvel.database import Model
from sqlalchemy import String


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
    published: Mapped[int] = mapped_column(default=0)
    view_count: Mapped[str] = mapped_column(String(20), default="0")
    meta: Mapped[str] = mapped_column(String(500), default="{}")
    published_at: Mapped[str] = mapped_column(String(40), default=None)
    expires_on: Mapped[str] = mapped_column(String(10), default=None)
    queued_at: Mapped[int] = mapped_column(default=0)
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

## Default values

```python
class Post(Model):
    published: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
```

For dynamic defaults (timestamps, UUIDs), pass a callable. The framework provides shortcuts:

```python
from arvel.database import Timestamps, Uuid


class Post(Model, Timestamps):
    id: Mapped[str] = mapped_column(Uuid, primary_key=True)
```

`Timestamps` adds `created_at` / `updated_at` and manages them on save. `Uuid` defaults to a fresh UUIDv7 (time-ordered) per row.

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
class User(Model):
    country_code: Mapped[str] = mapped_column(UpperString(2))
```

Now `user.country_code = "us"` stores `"US"`.

## Where to next?

- [ORM Getting Started](index.md) — defining models.
- [Encryption](encryption.md) — the crypto behind `EncryptedType`.
- [Validation](validation.md) — Pydantic patterns used by `PydanticType`.
