# Arvent: Getting Started

Arvel ships with **Arvent**, an Eloquent-style ORM built on SQLAlchemy. It gives you typed `Model` classes with an ActiveRecord flavor, a fluent `QueryBuilder[T]`, a Laravel-style `Schema` DSL that compiles to Alembic operations, lifecycle events, casts, factories, and seeders.

Arvent deliberately does **not** ship its own ORM core. Every `Model` is a SQLAlchemy `DeclarativeBase`, every `QueryBuilder` composes a `sqlalchemy.Select`, and every migration is an Alembic operation under the hood. Arvent is sugar — but type-safe, async-first sugar.

## Defining a model

```python
from arvel.database import Mapped

from arvel.database import Model, SoftDeletes, Timestamps, id_, string, text


class Post(Model, Timestamps, SoftDeletes):
    __tablename__ = "posts"

    id: Mapped[int] = id_()
    title: Mapped[str] = string(200)
    body: Mapped[str] = text()
```

The helpers in [`arvel.database.columns`](#typed-column-helpers) — `id_`, `string`, `text`, `integer`, `big_integer`, `boolean`, `datetime`, `json`, `foreign_id` — are thin wrappers around `mapped_column(...)` that return `Mapped[T]`. They mirror the [migration DSL](migrations.md) vocabulary, so model code and `make:migration` output line up by inspection.

`Timestamps` adds `created_at` / `updated_at` columns and manages them automatically on insert/update. `SoftDeletes` adds a `deleted_at` column and silently excludes soft-deleted rows from every query unless you call `.with_trashed()`.

### Typed column helpers

| Helper | SQL type | Equivalent `mapped_column(...)` |
|---|---|---|
| `id_(*, autoincrement=True)` | `INTEGER PRIMARY KEY` | `mapped_column(Integer, primary_key=True, autoincrement=...)` |
| `string(length=255, *, nullable=False, unique=False, index=False, default=None)` | `VARCHAR(length)` | `mapped_column(String(length), ...)` |
| `text(*, nullable=False, default=None)` | `TEXT` | `mapped_column(Text, ...)` |
| `integer(*, nullable=False, default=None, index=False)` | `INTEGER` | `mapped_column(Integer, ...)` |
| `big_integer(*, nullable=False, default=None, index=False)` | `BIGINT` | `mapped_column(BigInteger, ...)` |
| `boolean(*, nullable=False, default=None)` | `BOOLEAN` | `mapped_column(Boolean, ...)` |
| `datetime(*, nullable=False, default=None, index=False)` | `TIMESTAMP` | `mapped_column(DateTime, ...)` |
| `json(*, nullable=False, default=None)` | `JSON` / `JSONB` | `mapped_column(JSON, ...)` |
| `foreign_id(references, *, on="id", nullable=False, index=True, ondelete=None)` | `INTEGER REFERENCES …` | `mapped_column(ForeignKey(...), ...)` |

> **Email validation belongs at the API boundary, not on the column.** Use `string(254, unique=True)` for the model, and `EmailStr` on your Pydantic input schemas (`UserCreate`, `UserUpdate`). The storage layer stays plain VARCHAR — indexed, simple, fast — and the validation runs once at the boundary where invalid input is caught and rejected with a 422. See the [Email validation](#email-validation) section below and [ADR-077](https://github.com/mohamed-rekiba/arvel/blob/main/docs/adr/ADR-077-email-validation-at-boundary.md) for the rationale.

The helpers are additive — fall back to `mapped_column(...)` whenever you need something the helpers don't cover (custom server-side defaults, computed columns, dialect-specific types):

```python
from sqlalchemy import JSON, String
from arvel.database import Mapped, mapped_column

from arvel.database import Model, Timestamps, id_, string


class Profile(Model, Timestamps):
    __tablename__ = "profiles"

    id: Mapped[int] = id_()
    display_name: Mapped[str] = string(120)

    # Drop down to mapped_column when a column needs something the helpers don't cover.
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)
```

### Email validation

Emails persist as plain VARCHAR. Validation happens at the API boundary with Pydantic's `EmailStr`, not on the column. This is deliberate — see [ADR-077](https://github.com/mohamed-rekiba/arvel/blob/main/docs/adr/ADR-077-email-validation-at-boundary.md) for the full rationale.

**Model side** — a normal `string(254, unique=True)` column:

```python
from arvel.database import Mapped, Model, Timestamps, id_, string


class User(Model, Timestamps):
    __tablename__ = "users"

    id: Mapped[int] = id_()
    name: Mapped[str] = string(255)
    email: Mapped[str] = string(254, unique=True)
```

The `UNIQUE` constraint already implies a unique index — no separate `index=True` needed. Length `254` is the practical RFC-5321 maximum.

**Boundary side** — `EmailStr` on the Pydantic schemas that accept user input:

```python
from pydantic import BaseModel, ConfigDict, EmailStr


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    email: EmailStr            # RFC-5322 validation, friendly error messages


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = None
    email: EmailStr | None = None
```

`make:schema` does this automatically — any string column named `email` or ending in `_email` (e.g. `billing_email`, `contact_email`) gets `EmailStr` in the generated `Read`/`Create`/`Update` schemas:

```bash
uv run arvel make:schema User
# app/schemas/user_schema.py now imports EmailStr and types `email` accordingly
```

To opt a `*_email` column out of the upgrade, edit the generated schema (it's marked as user-editable).

**Migration side** — the matching schema-DSL call:

```python
def up(self, t: Blueprint) -> None:
    t.id()
    t.string("name", 255)
    t.string("email", 254).unique()
    t.timestamps()
```

### Generating a model

`make:model` writes the canonical skeleton — typed primary key, sample column, `Timestamps` mixin pre-mounted, the new column helpers imported:

```bash
uv run arvel make:model Post
```

```python
# app/models/Post.py
"""Post — ORM model."""

from __future__ import annotations

from arvel.database import Mapped, Model, Timestamps, id_, string


class Post(Model, Timestamps):
    __tablename__ = "posts"

    id: Mapped[int] = id_()
    name: Mapped[str] = string(255)
```

Once the model exists, `make:schema` generates a matching Pydantic boundary:

```bash
uv run arvel make:schema Post
```

```python
# app/schemas/post_schema.py — auto-generated, regenerate with --force
class PostRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str

class PostCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str

class PostUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = None
```

Server-managed columns (auto-increment PKs, `created_at`, `updated_at`, `deleted_at`) are excluded from `Create` and `Update`. Columns listed in `__hidden__` are excluded from all three.

## Working with rows

The ActiveRecord mixin gives you:

```python
post = await Post.create(title="hello", body="world")
post = await Post.find(post.id)
post = await Post.find_or_fail(post.id)

post.fill(title="edited", body="...")  # mass-assign (honours __fillable__/__guarded__)
await post.save()
await post.delete()                # soft delete (if SoftDeletes is mixed in)
await post.force_delete()          # hard delete
await post.restore()               # un-soft-delete

fresh = await post.fresh()         # reload from DB into a new instance
await post.refresh()               # in-place reload

clone = await post.replicate()     # unsaved copy: no PK, no timestamps, not trashed
```

`replicate()` drops the primary key, `created_at` / `updated_at`, and the
soft-delete column by default. Pass `except_=[...]` to skip extra fields.

### Dirty tracking

Like Eloquent, models track which attributes changed since they were loaded or last saved:

```python
post = await Post.find_or_fail(1)
post.title = "New title"

post.is_dirty()            # True
post.is_dirty("title")     # True
post.is_dirty("body")      # False
post.is_clean()            # False
post.get_dirty()           # {"title": "New title"}
post.get_original("title") # original DB value, ignoring the unsaved change

await post.save()

post.is_dirty()            # False — save resyncs the baseline
post.was_changed("title")  # True — the last save touched title
post.get_changes()         # {"title": "New title"}
```

`get_original()` with no argument returns every column's loaded value. `sync_original()` resets the baseline to the current values without hitting the DB.

### Get-or-create helpers

These mirror Laravel's `firstOrCreate` / `firstOrNew` / `updateOrCreate`. The
first argument is the attributes to match on; the second is extra values used
only when creating. The searched attributes are always merged into the new row:

```python
# Find by email, or create with email + name. The email is persisted too.
user = await User.first_or_create({"email": "a@b.com"}, {"name": "Alice"})

# Same lookup, but returns an unsaved instance you can tweak before save().
user = await User.first_or_new({"email": "a@b.com"}, {"name": "Alice"})

# Match on email; update name if found, otherwise create with both.
user = await User.update_or_create({"email": "a@b.com"}, {"name": "Alice"})
```

## QueryBuilder

Model classmethods return a typed `QueryBuilder[Post]`. Every builder method returns the builder (so chaining is type-safe) and every terminal method (`first`, `get`, `count`, `paginate`, `chunk`) is async:

```python
posts = await (
    Post.where(published=True)
    .where_in("category", ("python", "web"))
    .order_by("-created_at")
    .limit(10)
    .get()
)

page  = await Post.paginate(page=1, per_page=20)
total = await Post.where(published=True).count()

async def handle(batch: list[Post]) -> None:
    for post in batch:
        ...

await Post.chunk(100, handle)
```

The kwarg-shorthand for `where(field=value)` resolves the column via `getattr(Model, field)` and binds the value as a parameter — there's no string interpolation, so SQL injection is structurally impossible. This is verified by the framework's security tests.

A few Eloquent conveniences round out the builder:

```python
# first_where — add a constraint and grab the first row in one call
admin = await User.first_where(User.role == "admin")

# where_relation — filter parents by a related model's column
authors = await Author.where_relation("books", "genre", "scifi").all()

# bulk increment/decrement return rows affected, take extra columns, and
# touch updated_at on timestamped models (just like Eloquent's bulk update)
n = await Post.where(published=True).increment("views", 1, extra={"trending": True})
```

## Eager loading

```python
posts = await Post.with_("author", "comments").get()
```

Unknown relations raise `RelationNotLoadedError` at runtime — no silent N+1. See [Relationships](arvent-relationships.md).

## Casts

```python
from enum import StrEnum
from pydantic import BaseModel
from arvel.database import Mapped, mapped_column

from arvel.database import EncryptedType, EnumType, Model, PydanticType, id_


class Settings(BaseModel):
    theme: str = "light"


class Status(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"


class User(Model):
    __tablename__ = "users"
    id: Mapped[int] = id_()
    settings: Mapped[Settings] = mapped_column(PydanticType(Settings))
    status: Mapped[Status] = mapped_column(EnumType(Status))
    secret: Mapped[str] = mapped_column(EncryptedType(key_b64=...))
```

`EncryptedType` uses AES-GCM envelope encryption with a per-row IV (random mode) or a deterministic IV (search mode). See [Encryption](encryption.md) and ADR-014 for the threat model.

See [Mutators / Casts](arvent-mutators.md) for the full catalog.

## Lifecycle events & observers

Register an `Observer` on the model class. Hooks can be sync or async.

```python
from arvel.database import Observer


class PostObserver(Observer):
    async def creating(self, post: Post) -> None:
        post.slug = h.slug(post.title)

    async def updated(self, post: Post) -> None:
        ...


Post.observe(PostObserver())
```

Pass an observer **class** to resolve it from the app container (constructor
dependencies auto-wired after ``DatabaseServiceProvider`` boots):

```python
# app/providers/app_service_provider.py — boot()
Post.observe(PostObserver)
```

`create()`, `save()`, and `delete()` fire these events:

| Phase | New record | Existing record | Delete | Restore |
|---|---|---|---|---|
| Before | `creating` | `updating` | `deleting` | `restoring` |
| After | `created` | `updated` | `deleted` | `restored` |

All writes also emit `saving` / `saved`. Every read that hydrates a model emits
`retrieved` — once per row, whether you call `find`, `first`, `get`, `all`,
`sole`, `paginate`, or `chunk`. `force_delete()` fires `deleting` / `deleted`,
and `restore()` fires `restoring` / `restored`.

Return `False` from `creating`, `updating`, `deleting`, or `restoring` to abort
the pending operation. Arvel raises `OperationCancelledError` and does not flush
the change.

```python
from arvel.database.exceptions import OperationCancelledError


class Guard(Observer):
    def updating(self, post: Post) -> bool:
        return post.is_published  # False cancels save
```

## Service provider & request-scoped transactions

The `DatabaseServiceProvider` binds the engine, session maker, and an active session into the DI container, and registers the `Schema` executor binding. Add it to your app:

```python
from arvel import Application
from arvel.providers import (
    ConfigServiceProvider,
    DatabaseServiceProvider,
    HttpServiceProvider,
)


app = (
    Application.configure(base_path)
    .with_environment("local")
    .with_providers([ConfigServiceProvider, DatabaseServiceProvider, HttpServiceProvider])
    .create()
)
```

For request-scoped transactions, attach the `DatabaseTransaction` middleware (the **only** sanctioned bridge between `arvel.http` and `arvel.database` — see ADR-016):

```python
from arvel import Route
from arvel.http.middleware import DatabaseTransaction


@Route.post("/posts", middleware=[DatabaseTransaction()])
async def store(form: StorePost) -> dict:
    return (await Post.create(**form.validated().model_dump())).to_dict()
```

The middleware opens a transaction on entry, commits on a 2xx response, and rolls back on a 5xx or any unhandled exception.

## Soft deletes — query control

When `SoftDeletes` is mixed in, every query automatically excludes soft-deleted rows. Use these builder methods to override that behaviour:

```python
# Include soft-deleted rows
all_posts = await Post.with_trashed().get()

# Only soft-deleted rows
trash = await Post.only_trashed().get()
trash_count = await Post.only_trashed().count()
```

## Prunable

The `Prunable` mixin lets `arvel model:prune` delete stale rows on a schedule. Implement `prunable_query()` to return a `QueryBuilder` selecting the rows to remove:

```python
from datetime import UTC, timedelta
from datetime import datetime as dt

from arvel.database import Model, Prunable, Timestamps


class AuditLog(Model, Timestamps, Prunable):
    __tablename__ = "audit_logs"

    def prunable_query(self) -> QueryBuilder:  # type: ignore[override]
        cutoff = dt.now(UTC) - timedelta(days=90)
        return type(self).query().where(type(self).created_at < cutoff)
```

Then wire `model:prune` into the scheduler to keep the table lean:

```python
class ScheduleServiceProvider(ServiceProvider):
    async def boot(self) -> None:
        Schedule.command("model:prune").daily().at("03:00")
```

`model:prune` walks the SQLAlchemy mapper registry, finds every concrete `Prunable` subclass, calls `.prunable_query().delete()` on each, and prints a row count per model.

## Local query scopes

Encapsulate reusable query fragments as methods on the model. Define a
method named `scope_{name}` that takes `(self, query, *args)` and returns
the modified query, then call it as `Post.{name}()` or chain it onto a
query builder.

```python
class Post(Model):
    __tablename__ = "posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    category: Mapped[str] = mapped_column(String(20), nullable=False, default="general")

    def scope_active(self, query):
        return query.where(Post.status == "active")

    def scope_in_category(self, query, category: str):
        return query.where(Post.category == category)
```

```python
# Class-level entry — auto-creates a fresh QueryBuilder
active_posts = await Post.active().all()

# Chain multiple scopes
recent = await Post.active().in_category("news").order_by_desc("id").all()

# Or start from query() and chain
fresh = await Post.query().active().limit(10).get()
```

`self` is a bare instance (allocated via `object.__new__(cls)`) — useful
for ergonomics but not for reading instance state. Reference the class
directly (`Post.status`) inside the scope body. If you don't need the
`self` parameter, mark the method `@staticmethod` and drop it; the
framework still discovers `scope_*` static and class methods and
dispatches accordingly.

The explicit `@scope` decorator is still supported (see
[arvent-mutators.md](arvent-mutators.md)) — pick whichever shape reads
better in your model.

## Global scopes

A global scope applies a constraint to every query on a model. Multi-tenancy filters, soft-delete tombstones, and "only-published" defaults are the canonical use cases. Register them programmatically — either as a callable or as a [`GlobalScope`][arvel.database.GlobalScope] subclass.

### Registering with a callable

```python
from arvel.database import Model, QueryBuilder
from typing import Any


class Post(Model):
    __tablename__ = "posts"
    title: Mapped[str] = string(80)
    tenant_id: Mapped[str] = string(40)


def _tenant_filter(qb: QueryBuilder[Any]) -> QueryBuilder[Any]:
    return qb.where(Post.tenant_id == current_tenant_id())


Post.add_global_scope("tenant", _tenant_filter)
```

Every subsequent `Post.query()` (and the class-level shortcuts `Post.all()`, `Post.find(id)`, `Post.where(...)`) applies the scope.

### Registering with a `GlobalScope` subclass

A class is cleaner when the scope carries state:

```python
from arvel.database import GlobalScope, Model, QueryBuilder


class OnlyPublishedScope(GlobalScope):
    def __init__(self, column: str = "published_at") -> None:
        self.column = column

    def apply(self, qb: QueryBuilder[Any]) -> QueryBuilder[Any]:
        col = getattr(qb.model, self.column)
        return qb.where(col.is_not(None))


Post.add_global_scope("published", OnlyPublishedScope())
```

`qb.model` is a public read-only property that returns the model class the builder targets — use it inside `apply()` to resolve columns.

### Bypassing scopes

```python
# Skip one scope for this query only
all_posts = await Post.without_global_scope("tenant").get()

# Skip every registered scope
unfiltered = await Post.without_global_scopes().get()
```

The name you pass must match the string used in `add_global_scope()`.

### Inheritance

Subclasses inherit a parent's global scopes through normal MRO lookup:

```python
class Animal(Model):
    __abstract__ = True


Animal.add_global_scope("not_archived", lambda qb: qb.where(Animal.archived.is_(False)))


class Dog(Animal):
    __tablename__ = "dogs"
    name: Mapped[str] = string(40)


await Dog.all()    # applies "not_archived"
```

The first `add_global_scope` call on the subclass shallow-copies the inherited scope dict, so registering on `Dog` afterwards does not mutate `Animal`.

### Soft deletes use a global scope

The [`SoftDeletes`][arvel.database.SoftDeletes] mixin registers a [`SoftDeleteScope`][arvel.database.SoftDeleteScope] instance under the name `"soft_delete"`. Use `.with_trashed()` / `.only_trashed()` on the query builder to bypass it.

## Abstract mixins with `column_attr`

When you want to share columns across multiple concrete models (e.g. a `ProductBase` abstract mixin used by both `Product` and `ProductCatalog`), you can't use the regular column helpers directly — `MappedAsDataclass` sees them as dataclass fields and includes them in `__init__`, which breaks the mixin pattern.

`column_attr` is a `@declared_attr` variant that wraps the return annotation in `Mapped[T]` automatically, so the method is treated as an ORM mapping — not a dataclass field:

```python
from __future__ import annotations

import uuid

from arvel.database import Model, column_attr, uuid_id


class ProductBase:
    """Shared columns for both the write-side Product and read-side ProductCatalog."""

    @column_attr
    def id(self) -> uuid.UUID:
        return uuid_id(init=False)

    @column_attr
    def name(self) -> dict:
        return jsonb(default=dict)

    @column_attr
    def slug(self) -> dict:
        return jsonb(default=dict)


class Product(ProductBase, Model, Timestamps, SoftDeletes):
    __tablename__ = "products"


class ProductCatalog(ProductBase, ViewModel):
    __tablename__ = "v_published_products"
```

The return annotation can be a plain type (`uuid.UUID`, `str`, `dict`) — no need to wrap it in `Mapped[...]`. Works with or without `from __future__ import annotations`.

## View models

Map a `ViewModel` to an existing database view to get the full read-only query
API. All SELECT paths work identically to a regular model — `find`, `first`,
`where`, `paginate`, `chunk`, etc. Write paths (`create`, `save`, `delete`,
`insert`, `update`, `upsert`, `increment`, `decrement`) raise
`ReadOnlyModelError` before touching the database.

### Regular view

```python
from arvel.database import Mapped

from arvel.database import ViewModel, big_integer, id_


class ActiveUserStats(ViewModel):
    __tablename__ = "v_active_user_stats"   # must already exist in the DB

    id: Mapped[int] = id_()
    post_count: Mapped[int] = big_integer()
```

```python
stats = await ActiveUserStats.order_by("-post_count").limit(10).get()
top   = await ActiveUserStats.find_or_fail(user_id)

await ActiveUserStats.create(name="x")  # → ReadOnlyModelError
```

Generate the stub:

```bash
arvel make:model ActiveUserStats --view
```

### Materialized view (PostgreSQL)

Set `__is_materialized_view__ = True` to unlock `refresh_view()`, which emits
`REFRESH MATERIALIZED VIEW` via the active database connection.

```python
class DailyOrderStats(ViewModel):
    __tablename__ = "mv_daily_order_stats"
    __is_materialized_view__ = True

    date: Mapped[str] = id_()
    order_count: Mapped[int] = big_integer()
```

```python
await DailyOrderStats.refresh_view()                   # blocks until done
await DailyOrderStats.refresh_view(concurrently=True)  # non-blocking (requires UNIQUE index)
```

Calling `refresh_view()` on a regular view raises `ReadOnlyModelError`.

Generate the stub:

```bash
arvel make:model DailyOrderStats --materialized-view
```

The DDL to create the underlying view lives in a migration — see
[Views](migrations.md#views) and
[Materialized views](migrations.md#materialized-views-postgresql).

## Read-model policy

For materialized-view backed resources (e.g. `PublishedProduct` over `Product`), use
`ReadModelPolicy` in tests to enforce that storefront code never queries the write-side
model directly.

```python
from arvel.database import ReadModelPolicy, ReadModelPolicyViolation
from app.models import Product, PublishedProduct

policy = ReadModelPolicy(read_model=PublishedProduct, write_model=Product)

def test_cart_service_uses_published_boundary():
    with policy.guard():
        with pytest.raises(ReadModelPolicyViolation):
            # Any query that reaches Product._apply_global_scopes() raises.
            Product.query().where(Product.id == some_id)
```

`ImmutableReadModelError` is an alias for `ReadOnlyModelError` for callers who prefer
the read-model vocabulary.

See [Patterns: Domain Services & Read/Write Split](patterns.md) for the write-side pattern.

## Architecture & layering

A single architecture test enforces:

- `arvel.http` MUST NOT import `arvel.database`
- `arvel.database` MUST NOT import `arvel.http`
- The only exemption is `arvel.http.middleware.database_transaction`, the sanctioned bridge.

The test walks every `.py` file under both packages with the AST module, so any new cross-import fails the suite immediately.

## Where to next?

- [Relationships](arvent-relationships.md) — has-one, has-many, belongs-to, belongs-to-many, polymorphic.
- [Collections](collections.md) — the model-aware container returned by queries.
- [Mutators / Casts](arvent-mutators.md) — type conversion, encryption, JSON columns.
- [Factories](arvent-factories.md) — generating test data.
