# Models & CRUD

<a name="introduction"></a>
## Introduction

Arvel ships with **Arvent**, an active-record ORM built on top of SQLAlchemy's async engine. Each database table has a corresponding "model" you use to interact with that table. Models let you query for data in your tables, as well as insert, update, and delete records.

A model is a Python class. Its instances represent rows; its class methods build queries. Because Arvent sits on SQLAlchemy, a model is a real SQLAlchemy mapped class — you get the full power of SQLAlchemy underneath the Arvent surface.

> [!NOTE]
> Every persistence and read method on a model — `create`, `save`, `delete`, `find`, `all`, `first` — is an `async` coroutine and must be awaited. The fluent builder methods (`where`, `order_by`, `with_`) are synchronous and return a query builder; only the terminal method touches the database.

<a name="defining-models"></a>
## Defining Models

To get started, let's create a model. The easiest way is the `make:model` command:

```bash
arvel make:model Flight
```

This generates `app/models/flight.py`. A model declares typed attributes using the column helpers from `arvel.database`:

```python
from arvel.database import Model, Timestamps, id_, string


class Flight(Model, Timestamps):
    __tablename__ = "flights"

    id: int = id_()
    name: str = string(255)
```

On its own, `make:model` only creates the model class. To scaffold the related artifacts in one command, pass companion flags — each is named from the model:

| Flag | Companion |
|---|---|
| `-m`, `--migration` | A `create_<table>_table` migration (the table name is pluralized). |
| `-f`, `--factory` | A model factory. |
| `-s`, `--seed` | A database seeder. |
| `-c`, `--controller` | A controller (add `--resource` / `--api` to shape it). |
| `--requests` | The `Store…Request` / `Update…Request` pair. |
| `-p`, `--policy` | An authorization policy. |
| `-o`, `--observer` | A lifecycle observer. |
| `-R`, `--json-resource` | A `JsonResource` transformer. |
| `--test` | A feature test. |
| `-a`, `--all` | The model plus every companion above (resource controller). |

```bash
arvel make:model Flight -mfsc        # model + migration + factory + seeder + controller
arvel make:model Flight --all        # the full set
```

Companions that already exist are skipped, never overwritten. Short flags combine (`-mf`, `-mfsc`).

<a name="table-names"></a>
### Table Names

Unlike Eloquent, Arvent does **not** infer the table name from the class name. Every concrete model must declare `__tablename__` explicitly:

```python
class Flight(Model):
    __tablename__ = "my_flights"
    ...
```

> [!WARNING]
> Forgetting `__tablename__` is the most common first mistake. There is no runtime pluralization fallback on the model — the class will fail to map. (The CLI scaffolders *do* pluralize a class name into a suggested table name, but that's a generation-time convenience, not a runtime default.)

<a name="primary-keys"></a>
### Primary Keys

Use `id_()` for an auto-incrementing integer primary key, or `uuid_id()` for a UUID v7 key:

```python
from arvel.database import Model, id_, uuid_id
import uuid


class Flight(Model):
    __tablename__ = "flights"
    id: int = id_()


class Booking(Model):
    __tablename__ = "bookings"
    id: uuid.UUID = uuid_id()
```

Both default to `init=False` — the value is provided by the database (integer) or a default factory (UUID), so you never pass it to the constructor. Composite primary keys are supported; `find` accepts a tuple in that case.

<a name="column-helpers"></a>
### Column Helpers

The column helpers in `arvel.database` mirror the migration [Blueprint](migrations.md#available-column-types) vocabulary so the schema and the model speak the same language. They all return `Any`, so the plain annotation drives the Python type and the assignment stays clean under strict type checkers.

| Helper | Column type |
|---|---|
| `id_()` | Auto-increment integer primary key |
| `uuid_id()` | UUID v7 primary key |
| `string(length=255)` | `VARCHAR(length)` |
| `text()` | `TEXT` |
| `integer()` / `big_integer()` | `INTEGER` / `BIGINT` |
| `boolean()` | `BOOLEAN` |
| `decimal(precision=10, scale=2)` | `NUMERIC` |
| `datetime(timezone=True)` | `TIMESTAMP` |
| `json()` / `jsonb()` | `JSON` / `JSONB` (Postgres) |
| `uuid()` | UUID value column |
| `enum(EnumOrValues)` | `ENUM` |
| `foreign_id(references)` | Integer FK, e.g. `foreign_id("users.id")` |
| `foreign_uuid` / `foreign_string` | FKs for UUID / string primary keys |
| `column(SAType)` | Any SQLAlchemy type (custom `TypeDecorator`) |

Most helpers accept `nullable=`, `unique=`, `index=`, and `default=`:

```python
from decimal import Decimal
from arvel.database import Model, Timestamps, boolean, decimal, foreign_id, id_, string, text


class Post(Model, Timestamps):
    __tablename__ = "posts"

    id: int = id_()
    user_id: int = foreign_id("users.id", on_delete="CASCADE")
    title: str = string(200, index=True)
    body: str = text()
    price: Decimal = decimal(10, 2)
    is_published: bool = boolean(default=False)
```

<a name="inferred-columns"></a>
### Inferred Columns

For the common case you don't need a helper at all. The model metaclass infers a column from a bare annotation or a plain default:

```python
class Post(Model):
    __tablename__ = "posts"
    id: int = id_()

    title: str                     # → VARCHAR(255), NOT NULL
    views: int = 0                 # → INTEGER, default 0
    published_at: datetime | None = None   # → nullable, tz-aware TIMESTAMP
```

When you need an option a bare annotation can't carry — a unique index, a foreign key, an explicit length — reach for `field(...)`:

```python
from arvel.database import field

handle: str = field(length=64, unique=True, index=True)
team_id: int = field(foreign_key="teams.id", on_delete="CASCADE")
```

<a name="timestamps"></a>
### Timestamps

Add the `Timestamps` mixin to get `created_at` and `updated_at` columns that Arvent maintains automatically — set on insert, bumped on update:

```python
class Flight(Model, Timestamps):
    __tablename__ = "flights"
    id: int = id_()
```

To bump `updated_at` without otherwise changing the row, call `await model.touch()`. To run a block of work without touching timestamps:

```python
async with Flight.without_timestamps():
    await flight.save()
```

<a name="default-attribute-values"></a>
### Default Attribute Values

A column without a default becomes a **required** keyword argument in the model's generated constructor (models are keyword-only dataclasses). Supply a `default=` to make it optional:

```python
name: str = string(255)                    # required: Flight(name=...)
slug: str | None = string(255, default=None)   # optional
```

<a name="retrieving-models"></a>
## Retrieving Models

Once you have a model and its table, you can start retrieving data. Each model serves as a query builder entry point. The `all` method retrieves every row:

```python
flights = await Flight.all()

for flight in flights:
    print(flight.name)
```

The model's query methods (`where`, `order_by`, …) return a [query builder](query-builder.md). Add constraints, then run the query with a terminal method like `get`:

```python
flights = await (
    Flight.where(active=True)
    .order_by("-name")
    .limit(10)
    .get()
)
```

<a name="collections"></a>
### Collections

`all` and `get` return a `ModelCollection` — a `list` subclass enriched with helpers like `pluck`, `map`, `filter`, `group_by`, `key_by`, and `first_where`. Because it's a list, you can iterate it, index it, and pass it anywhere a list is expected:

```python
flights = await Flight.where(active=True).get()

names = flights.pluck("name")
grounded = flights.filter(lambda f: not f.active)
```

See [Collections](query-builder.md#collections) for the full method list.

<a name="retrieving-single-models"></a>
### Retrieving Single Models

In addition to retrieving all rows matching a query, you can fetch single records with `find`, `first`, and `first_where`:

```python
flight = await Flight.find(1)                       # by primary key, or None
flight = await Flight.where(active=True).first()     # first match, or None
flight = await Flight.query().first_where(name="LA") # shorthand
```

`pluck`, `value`, and aggregates pull single columns or scalars:

```python
names = await Flight.query().pluck("name")          # list of one column
total = await Flight.where(active=True).count()
```

<a name="not-found-behavior"></a>
### Not Found Behavior

Sometimes you want to raise instead of receiving `None`. The `*_or_fail` methods raise `ModelNotFoundError`:

```python
flight = await Flight.find_or_fail(1)
flight = await Flight.where(legs=3).first_or_fail()
```

> [!NOTE]
> If you don't catch `ModelNotFoundError` in an HTTP handler, the framework's [exception handler](../the-basics/error-handling.md) translates it into a `404 Not Found` JSON response automatically.

<a name="inserting-and-updating-models"></a>
## Inserting & Updating Models

<a name="inserts"></a>
### Inserts

To insert a new record, create an instance, set its attributes, and call `save`:

```python
flight = Flight(name="London to Paris")
await flight.save()
```

Or do it in one step with `create`, which accepts the attributes as keyword arguments:

```python
flight = await Flight.create(name="London to Paris")
```

`created_at` and `updated_at` are set automatically when the model uses `Timestamps`.

<a name="updates"></a>
### Updates

There is **no** instance-level `update(**attrs)` method. To update an existing model, set its attributes (or `fill` them) and call `save`:

```python
flight = await Flight.find_or_fail(1)
flight.name = "Paris to London"
await flight.save()
```

> [!WARNING]
> `Flight.update({...})` on the **class** is a bulk query-builder update over many rows — not an instance update. Don't confuse the two:
> ```python
> # updates ALL matching rows in one statement
> await Flight.where(active=False).update({"active": True})
> ```

To update a single model without firing [model events](#model-events), use `update_quietly`:

```python
await flight.update_quietly(name="Paris to London")
```

<a name="mass-assignment"></a>
### Mass Assignment

`create` and `fill` go through mass-assignment protection. By default a model is **unguarded** — any attribute may be set. Lock it down with `__fillable__` (an allowlist) or `__guarded__` (a denylist):

```python
class Flight(Model):
    __tablename__ = "flights"
    __fillable__ = ["name", "destination"]   # only these may be mass-assigned

    id: int = id_()
    name: str = string(255)
    destination: str = string(255)
    is_admin_only: bool = boolean(default=False)
```

A disallowed key raises `MassAssignmentError`. To bypass guarding deliberately, use `force_fill` or the `unguarded` context manager:

```python
flight.force_fill(**untrusted)

with Flight.unguarded():
    flight.fill(**untrusted)
```

> [!NOTE]
> Constructing a model directly — `Flight(name=...)` — does **not** run mass-assignment checks. Guarding applies only to `create()` and `fill()`. Validate untrusted input with a [form request](../the-basics/validation.md) before it reaches the model.

<a name="upserts"></a>
### Upserts

Get-or-create patterns are available on the query builder:

```python
flight = await Flight.query().first_or_create(
    {"name": "London to Paris"},          # match attributes
    {"destination": "Paris"},             # extra values if creating
)

flight = await Flight.query().update_or_create(
    {"departure": "LHR", "destination": "CDG"},
    {"price": Decimal("99.00")},
)
```

For bulk upserts, see [Bulk Writes](query-builder.md#bulk-writes).

<a name="deleting-models"></a>
## Deleting Models

To delete a model, call `delete` on an instance:

```python
flight = await Flight.find_or_fail(1)
await flight.delete()
```

To delete many rows at once, run a delete through the query builder:

```python
await Flight.where(active=False).delete()
```

<a name="soft-deleting"></a>
### Soft Deleting

Add the `SoftDeletes` mixin to keep rows in the table but mark them deleted with a `deleted_at` timestamp. Soft-deleted rows are hidden from queries by default:

```python
from arvel.database import Model, Timestamps, SoftDeletes, id_, string


class Flight(Model, Timestamps, SoftDeletes):
    __tablename__ = "flights"
    id: int = id_()
    name: str = string(255)
```

Now `delete` sets `deleted_at` instead of removing the row:

```python
await flight.delete()           # sets deleted_at; row stays
flight.trashed()                # True
await flight.restore()          # clears deleted_at
await flight.force_delete()     # permanently removes the row
```

<a name="querying-soft-deleted-models"></a>
### Querying Soft Deleted Models

Soft deletes are enforced by a global scope, so ordinary queries exclude trashed rows. Include or isolate them explicitly:

```python
await Flight.with_trashed().get()    # include soft-deleted rows
await Flight.only_trashed().get()    # only the soft-deleted rows
```

Bulk restore must pair with `only_trashed` — otherwise the default scope hides the very rows you mean to restore:

```python
await Flight.only_trashed().restore()
```

<a name="dirty-tracking"></a>
## Dirty Tracking

After loading a model you can inspect what changed before saving, and what changed after the last save:

```python
flight = await Flight.find_or_fail(1)
flight.name = "New name"

flight.is_dirty()              # any unsaved changes?
flight.is_dirty("name")        # this attribute specifically?
flight.is_clean("destination") # unchanged?
flight.get_dirty()             # {"name": "New name"}
flight.get_original("name")    # value as loaded

await flight.save()
flight.was_changed("name")     # changed by the save just performed?
flight.get_changes()           # {attr: new_value} from the last save
```

<a name="model-mixins"></a>
## Model Mixins

Compose behavior by inheriting mixins alongside `Model`:

| Mixin | Adds |
|---|---|
| `Timestamps` | `created_at` / `updated_at`, maintained automatically |
| `SoftDeletes` | `deleted_at` column and soft-delete behavior |
| `HasUuids` | Auto-fills a string primary key with a UUID on insert |
| `HasUlids` | Auto-fills a string primary key with a ULID on insert |
| `Prunable` | Marks stale rows for pruning (you implement `prunable_query`) |

> [!NOTE]
> `Prunable.prunable_query()` raises `NotImplementedError` by default — you must override it to declare which rows are eligible for pruning.

<a name="model-events"></a>
## Model Events

Arvent models dispatch lifecycle events you can hook into. The "before" events — `creating`, `updating`, `deleting`, `restoring`, `force_deleting` — can **cancel** the operation by returning `False`. The "after" and ambient events — `saving`, `saved`, `created`, `updated`, `deleted`, `trashed`, `force_deleted`, `restored`, `retrieved`, `replicating` — fire around the operation.

<a name="observers"></a>
### Observers

Group event handlers into an observer class. Generate one with `arvel make:observer`, then register it:

```python
from arvel.database import Observer


class FlightObserver(Observer):
    def creating(self, flight: Flight) -> bool | None:
        if flight.name == "":
            return False          # cancels the insert

    async def created(self, flight: Flight) -> None:
        await notify_ops(flight)


Flight.observe(FlightObserver())
```

You can also register a single callback, or declare observers on the class:

```python
Flight.on("deleted", purge_cache)


class Flight(Model, Timestamps):
    __tablename__ = "flights"
    __observed_by__ = [FlightObserver]
```

To dispatch model events onto the application [event bus](../features/events.md), map them with `__dispatches_events__`.

<a name="muting-events"></a>
### Muting Events

Suppress all events for a block of work:

```python
async with Flight.without_events():
    await flight.save()
```

The `*_quietly` helpers (`save_quietly`, `delete_quietly`, `force_delete_quietly`, `restore_quietly`, `update_quietly`) do the same for a single operation.

<a name="serializing-models"></a>
## Serializing Models

Models convert to dictionaries and JSON for storage or transport:

```python
flight.to_dict()                 # respects __hidden__ / __visible__ / __appends__
flight.to_json(indent=2)
flight.to_pydantic(FlightOut)    # validate into a Pydantic schema
flight.only("id", "name")
flight.except_("internal_notes")
```

Control which attributes appear with the `__hidden__` (denylist), `__visible__` (allowlist, applied first), and `__appends__` (computed accessor names) class variables, or per instance with `make_hidden(...)`, `make_visible(...)`, and `append(...)`:

```python
from arvel.database import Model, Timestamps, accessor, id_, string


class User(Model, Timestamps):
    __tablename__ = "users"
    __hidden__ = ["password_hash"]    # column dropped from output
    __appends__ = ["full_name"]       # accessor added to output

    id: int = id_()
    first_name: str = string(50)
    last_name: str = string(50)

    # full_name isn't a column — it's a computed accessor. __appends__ tells
    # to_dict()/to_json() to include it. See Casts, Accessors & Mutators.
    @accessor
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"
```

`__appends__` only accepts names backed by an [accessor](casts.md#defining-an-accessor) (a `@accessor` method or an `Attribute` object) — `to_dict()` resolves each name with `getattr(self, name)`, so an entry with no matching accessor raises `AttributeError`.

> [!NOTE]
> `to_dict()` serializes **columns only** — relationships are not included. To embed related data, load it and use `to_pydantic(schema)` with the relation named in the schema, or shape the output with an [API resource](../the-basics/resources.md), which is the recommended approach for HTTP responses.

Returning a model (or a list of models) straight from a route applies `__hidden__`/`__visible__` too — the response layer runs the same serialization, so a bare `return user` won't leak `password_hash`:

```python
@Route.get("/users/{id}")
async def show(id: int) -> User:
    return await User.find_or_fail(id)   # password_hash dropped automatically
```

This reaches models nested in the return value too — a `return {"user": user, "orders": [order, ...]}` hides `password_hash` on every model inside the dict, list, or tuple.

This only kicks in when the route has no explicit `response_model`. If you annotate one, your schema decides the shape — declare a schema that omits sensitive fields.

<a name="read-only-models"></a>
## Read-Only Models

For models that map to a database view (or that you never want written), extend `ViewModel`. It blocks `create`, `save`, `delete`, and `force_delete`:

```python
from arvel.database import ViewModel, id_, string


class MonthlyRevenue(ViewModel):
    __tablename__ = "monthly_revenue"
    id: int = id_()
    month: str = string(7)
```

Generate one with `arvel make:model MonthlyRevenue --view` (or `--materialized-view`).
