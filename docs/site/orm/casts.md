# Casts, Accessors & Mutators

<a name="introduction"></a>
## Introduction

Accessors, mutators, and attribute casting let you transform model attribute values when you read or write them. **Casts** convert a column between its stored form and a richer Python type automatically — JSON text becomes a `dict`, a numeric string becomes a `Decimal`, ciphertext becomes plaintext. **Accessors** and **mutators** add computed attributes or transform a value as it's set.

These three mechanisms overlap with what plain Python types and SQLAlchemy already give you. Reach for them when you want behavior the column type alone can't express: a fixed-scale decimal, an encrypted value, a derived attribute, or input normalization.

<a name="attribute-casting"></a>
## Attribute Casting

<a name="declaring-casts"></a>
### Declaring Casts

Define a `__casts__` class variable mapping attribute names to a cast specification:

```python
from decimal import Decimal
from typing import Any, ClassVar
from arvel.database import Model, decimal, id_, string, text


class Doc(Model):
    __tablename__ = "docs"

    id: int = id_()
    code: str = string(20)
    meta: str = text()
    flag: str = string(5)
    price: Decimal = decimal(10, 2)

    __casts__: ClassVar[dict[str, Any]] = {
        "meta": "dict",        # JSON text <-> dict
        "flag": "boolean",
        "price": "decimal:2",  # parameterized
    }
```

Now `doc.meta` reads as a `dict`, and assigning a `dict` serializes back to the column. `doc.flag` reads as a `bool`. Casts run on attribute read and write, and again (via a `serialize` step) when the model is converted with `to_dict()`.

<a name="built-in-cast-strings"></a>
### Built-in Cast Strings

| Spec | On read | On write |
|---|---|---|
| `boolean` / `bool` | `bool` (Laravel-style: `"0"`, `""` → `False`) | same |
| `integer` / `int` | `int` | same |
| `float` | `float` | same |
| `string` / `str` | `str` | same |
| `dict` / `list` / `array` | parsed JSON | stored as-is |
| `object` | `SimpleNamespace` | — |
| `collection` | a `Collection` wrapper | — |
| `datetime` | UTC-aware `datetime` | same |
| `date` | `date` | same |
| `timestamp` | integer epoch seconds | same |
| `hashed` | — (read passes through) | hashed via the `Hash` facade |

> [!NOTE]
> The `hashed` cast hashes the value on write but does not transform it on read — so an assigned plaintext password becomes a one-way hash in the column, and reading returns the stored hash. This is the right behavior for password columns.

<a name="parameterized-casts"></a>
### Parameterized Casts

Some casts take a parameter after a colon:

| Spec | Behavior |
|---|---|
| `decimal:N` | `Decimal` quantized to `N` places (`ROUND_HALF_UP`) |
| `datetime:FORMAT` | parse/serialize with a `strftime` format |
| `encrypted` / `encrypted:string` | encrypt/decrypt a string |
| `encrypted:json` / `encrypted:array` | encrypt/decrypt a JSON value |
| `encrypted:object` | encrypt/decrypt → `SimpleNamespace` |
| `encrypted:collection` | encrypt/decrypt → `Collection` |

```python
__casts__: ClassVar[dict[str, Any]] = {
    "price": "decimal:2",
    "starts_at": "datetime:%Y-%m-%d %H:%M",
}
```

> [!WARNING]
> An invalid `encrypted:*` variant raises `ValueError` at **class definition time**, not at runtime — so a typo fails fast when the module is imported.

<a name="enum-casting"></a>
### Enum Casting

Pass an `Enum` subclass directly as the cast spec. Reading returns the enum member; writing and serializing use the backing value:

```python
import enum


class Status(str, enum.Enum):
    draft = "draft"
    published = "published"


class Post(Model):
    __tablename__ = "posts"
    id: int = id_()
    status: str = string(20)

    __casts__: ClassVar[dict[str, Any]] = {"status": Status}
```

<a name="encrypted-casting"></a>
## Encrypted Casting

The `encrypted:*` casts encrypt the attribute before it's written and decrypt it on read, using the application [encrypter](../features/encryption.md). The encrypter is built from your `APP_KEY`:

```python
from typing import Any, ClassVar
from sqlalchemy import String, Text
from arvel.database import Model, column, id_


class Account(Model):
    __tablename__ = "accounts"
    id: int = id_()
    ssn: Any = column(String(512))
    preferences: Any = column(Text)

    __casts__: ClassVar[dict[str, Any]] = {
        "ssn": "encrypted",
        "preferences": "encrypted:array",
    }
```

```python
account.ssn = "123-45-6789"   # stored encrypted
await account.save()
account.ssn                    # reads back decrypted
```

> [!WARNING]
> Encrypted casts require `APP_KEY` to be set — they raise `MissingAppKeyError` otherwise. Generate one with `arvel key:generate`. Note that **rotating** the key makes existing ciphertext unreadable; plan key rotation carefully. See [Encryption](../features/encryption.md).

<a name="custom-casts"></a>
## Custom Casts

For reusable conversion logic, implement the `CastsAttributes` protocol. It has three methods — `get` (read), `set` (write), and an optional `serialize` (for `to_dict`):

```python
from typing import Any
from arvel.database import CastsAttributes


class AsUpper(CastsAttributes):
    def get(self, model: Any, key: str, value: Any) -> Any:
        return value.upper() if value else value

    def set(self, model: Any, key: str, value: Any) -> Any:
        return value.lower() if value else value

    def serialize(self, model: Any, key: str, value: Any) -> Any:
        return value
```

Use either an instance or the class as the spec value:

```python
class Doc(Model):
    __tablename__ = "docs"
    id: int = id_()
    code: str = string(20)

    __casts__: ClassVar[dict[str, Any]] = {"code": AsUpper()}   # or AsUpper
```

Generate a cast scaffold with `arvel make:cast`.

<a name="column-level-types"></a>
## Column-Level Types

Casting transforms values in Python. When you'd rather handle the conversion at the SQLAlchemy column level — so the storage representation is part of the column type itself — use a `TypeDecorator` with the `column(...)` helper:

| Type | Stores |
|---|---|
| `PydanticType(Model)` | A Pydantic model as JSON / JSONB |
| `EnumType(EnumCls)` | The enum's backing value as a string |
| `EncryptedType(key, *, deterministic=False)` | An AES-256-GCM encrypted value |

```python
from arvel.database import Model, column, id_
from arvel.database.casts import EncryptedType, PydanticType


class Secret(Model):
    __tablename__ = "secrets"

    id: int = id_()
    token: str = column(EncryptedType(key))            # key is a 32-byte value
    profile: Profile | None = column(PydanticType(Profile), nullable=True, default=None)
```

> [!NOTE]
> `EncryptedType` takes a raw 32-byte key in its constructor — it is **not** wired to `APP_KEY` automatically, unlike the `encrypted:*` attribute casts. Use the attribute cast when you want the app key; use `EncryptedType` when you manage the key yourself.

<a name="accessors-and-mutators"></a>
## Accessors & Mutators

<a name="defining-an-accessor"></a>
### Defining an Accessor

An accessor is a computed, read-only attribute. Decorate a method with `@accessor`:

```python
from arvel.database import Model, accessor, id_, string


class User(Model):
    __tablename__ = "users"
    id: int = id_()
    first_name: str = string(50)
    last_name: str = string(50)

    @accessor
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"
```

```python
user.full_name   # "Grace Hopper"
```

<a name="defining-a-mutator"></a>
### Defining a Mutator

A mutator transforms a value before it's assigned to a column. Decorate a method with `@mutator("column_name")`. It runs **before** any cast on that column:

```python
from arvel.database import mutator


class User(Model):
    __tablename__ = "users"
    id: int = id_()
    email: str = string(255)

    @mutator("email")
    def normalize_email(self, value: str) -> str:
        return value.strip().lower()
```

<a name="attribute-objects"></a>
### Attribute Objects

When a single attribute needs both a getter and a setter — including a setter that writes to multiple columns — use an `Attribute` object. Its setter must return a mapping of column → value:

```python
from arvel.database import Attribute


def _split_name(_model: "User", value: str) -> dict[str, str]:
    first, _, last = value.partition(" ")
    return {"first_name": first, "last_name": last}


class User(Model):
    __tablename__ = "users"
    id: int = id_()
    first_name: str = string(50)
    last_name: str = string(50)

    full_name = Attribute.make(
        get=lambda m: f"{m.first_name} {m.last_name}".strip(),
        set=_split_name,
    )
```

Call `.should_cache()` on the attribute to memoize the computed value per instance.

<a name="appending-accessors-to-output"></a>
### Appending Accessors to Output

Accessors are not included in `to_dict()` by default — they aren't columns. Add them to `__appends__`, or append per instance:

```python
class User(Model):
    __tablename__ = "users"
    __appends__ = ["full_name"]

    id: int = id_()
    first_name: str = string(50)
    last_name: str = string(50)

    @accessor
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"
```

Every name in `__appends__` must resolve to an accessor — `to_dict()` reads each with `getattr(self, name)`. You can also append on a single instance instead of for the whole class:

```python
user.append("full_name")
user.to_dict()    # now includes "full_name"
```
