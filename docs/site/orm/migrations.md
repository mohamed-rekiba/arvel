# Migrations

<a name="introduction"></a>
## Introduction

Migrations are version control for your database. They let you define and share the application's schema as code. Arvel's schema DSL — `Schema` plus `Blueprint` — describes tables in Python and compiles them to Alembic operations under the hood, while a Laravel-style runner tracks which migrations have run and supports batch rollback.

<a name="generating-migrations"></a>
## Generating Migrations

Use the `make:migration` command. The framework derives the table name from the migration name and timestamps the file so migrations run in order:

```bash
arvel make:migration create_flights_table
```

Migrations are written to `database/migrations/`. Files are discovered and applied in lexicographic order (the timestamp prefix ensures correct ordering), and files whose names start with `_` are skipped.

<a name="migration-structure"></a>
## Migration Structure

A migration defines two module-level coroutines, `up` and `down`, that receive the `Schema`. `up` makes the change; `down` reverses it:

```python
from arvel.database import Blueprint, Schema


async def up(schema: Schema) -> None:
    def build(table: Blueprint) -> None:
        table.id()
        table.string("name", length=255)
        table.decimal("price", precision=10, scale=2)
        table.boolean("is_active").server_default("true")
        table.timestamps()

    Schema.create("flights", build)


async def down(schema: Schema) -> None:
    Schema.drop_if_exists("flights")
```

> [!WARNING]
> Although `up` and `down` are declared `async`, the `Schema` operations inside them are **synchronous** — you do not `await` them. The runner drives the coroutine in a single step, so performing a real `await` inside a migration body raises `RuntimeError`. Keep migration bodies to schema operations only.

A migration with foreign keys and indexes reads the same way — the relationships in your [models](models.md) map directly onto the schema:

```python
async def up(schema: Schema) -> None:
    def build(table: Blueprint) -> None:
        table.id()
        table.foreign_id("user_id").constrained().cascade_on_delete()
        table.string("title", length=200)
        table.text("body")
        table.string("status", length=20).server_default("draft")
        table.timestamps()
        table.soft_deletes()

        table.index("title")
        table.index(["status", "created_at"])      # composite index

    Schema.create("posts", build)


async def down(schema: Schema) -> None:
    Schema.drop_if_exists("posts")
```

<a name="running-migrations"></a>
## Running Migrations

```bash
arvel migrate              # apply all pending migrations
arvel migrate --dry-run    # print the SQL without applying it
arvel migrate:status       # show applied vs pending
```

<a name="rolling-back"></a>
### Rolling Back

Each `migrate` run is recorded as a "batch". Rolling back reverses the most recent batch; resetting reverses everything:

```bash
arvel migrate:rollback     # undo the last batch
arvel migrate:reset        # roll back every applied migration
```

<a name="refreshing-and-dropping"></a>
### Refreshing & Dropping

```bash
arvel migrate:refresh      # reset, then re-run all migrations
arvel migrate:fresh        # drop all tables, then re-run all migrations
```

Both accept `--seed` (run the default seeder afterward) and `--seeder NAME`.

> [!WARNING]
> `migrate:fresh` and `migrate:refresh` are destructive. They are **blocked when `app.env` is `production`** unless you set `ARVEL_ALLOW_DESTRUCTIVE=1`. Never set that against a database you care about. Note that `migrate` and `migrate:rollback` themselves have no production guard — they're considered safe forward/backward steps.

<a name="tables"></a>
## Tables

<a name="creating-tables"></a>
### Creating Tables

`Schema.create` takes the table name and a callback that receives a `Blueprint`:

```python
def build(table: Blueprint) -> None:
    table.id()
    table.string("email").unique()
    table.timestamps()

Schema.create("users", build)
```

<a name="updating-tables"></a>
### Updating Tables

Use `Schema.table` to alter an existing table — add columns, drop columns, add indexes:

```python
def build(table: Blueprint) -> None:
    table.string("phone").nullable()
    table.drop_column("legacy_field")

Schema.table("users", build)
```

<a name="dropping-tables"></a>
### Dropping Tables

```python
Schema.drop("users")
Schema.drop_if_exists("users")
```

> [!NOTE]
> `drop_if_exists` is currently an alias for `drop` — it does not yet emit `IF EXISTS`. Treat dropping a non-existent table as an error for now.

<a name="columns"></a>
## Columns

<a name="available-column-types"></a>
### Available Column Types

Inside a `build` callback, declare columns with the `Blueprint` methods:

| Method | Column |
|---|---|
| `table.id(name="id")` | Auto-increment integer primary key |
| `table.uuid(name)` / `table.ulid(name)` | UUID / ULID |
| `table.string(name, length=255)` | `VARCHAR` |
| `table.text(name)` / `medium_text` / `long_text` | Text columns |
| `table.integer(name)` / `big_integer` / `tiny_integer` | Integers |
| `table.boolean(name)` | Boolean |
| `table.float(name)` / `table.decimal(name, precision=10, scale=2)` | Numerics |
| `table.datetime(name, timezone=True)` | Timestamp |
| `table.json(name)` / `table.jsonb(name)` | JSON / JSONB |
| `table.binary(name)` | Binary blob |
| `table.enum(name, values)` | Enum |
| `table.ip_address(name)` | `VARCHAR(45)` |
| `table.foreign_id(name)` | Integer foreign-key column |
| `table.morphs(base)` | Polymorphic `{base}_type` + `{base}_id` (+ index) |
| `table.timestamps()` | `created_at` / `updated_at` |
| `table.soft_deletes(name="deleted_at")` | nullable `deleted_at` (+ partial index) |
| `table.tsvector(name)` | PostgreSQL full-text vector |

> [!NOTE]
> A couple of methods are intentionally simplified: `big_integer(...)` currently emits a plain `INTEGER` and its `unsigned` flag is ignored, and there is no singular `timestamp()` method (use `datetime(...)` or `timestamps()`).

<a name="column-modifiers"></a>
### Column Modifiers

Columns are fluent — chain modifiers onto a column definition:

```python
table.string("email", length=255).unique()
table.datetime("published_at").nullable()
table.integer("views").default(0)
table.boolean("active").server_default("true")
table.datetime("created_at").use_current()
```

| Modifier | Effect |
|---|---|
| `.nullable()` | Allow `NULL` |
| `.unique()` | Column-level unique constraint |
| `.primary()` / `.autoincrement()` | Primary key / auto-increment |
| `.default(value)` | Python-side default |
| `.server_default(value)` | Database-side default |
| `.use_current(on_update=False)` | `CURRENT_TIMESTAMP` default |

> [!NOTE]
> `.comment(...)` and `.after(...)` are accepted but currently **not emitted** in the generated DDL — they're placeholders. Don't rely on them.

<a name="foreign-keys"></a>
### Foreign Keys

Declare a foreign key with `foreign_id` and chain `constrained` plus a delete rule:

```python
table.foreign_id("user_id").constrained()                 # references users.id
table.foreign_id("team_id").constrained("teams").cascade_on_delete()
table.foreign_id("owner_id").nullable().null_on_delete()
```

`constrained()` infers the referenced table by pluralizing the `{name}_id` column. Delete-rule shorthands: `.cascade_on_delete()`, `.null_on_delete()`, `.restrict_on_delete()`, or the explicit `.on_delete(...)` / `.on_update(...)`.

<a name="indexes"></a>
## Indexes

```python
table.index(["last_name", "first_name"])
table.unique("email")
table.gin_index("documents", "search_vector")
table.expression_index("LOWER(email)", name="users_lower_email")

# drop helpers
table.drop_index("users_email_unique")
table.rename_column("old_name", "new_name")
```

Standalone (outside a `build` callback): `Schema.create_index(...)` and `Schema.create_expression_index(...)`.

<a name="pivot-tables"></a>
### Pivot Tables

A [many-to-many](relationships.md#many-to-many) relationship needs a pivot table. It's an ordinary table with two foreign keys and a composite primary key:

```python
async def up(schema: Schema) -> None:
    def build(table: Blueprint) -> None:
        table.foreign_id("post_id").constrained().cascade_on_delete().primary()
        table.foreign_id("tag_id").constrained().cascade_on_delete().primary()
        table.string("added_by", length=50).nullable()    # extra pivot column

    Schema.create("post_tag", build)
```

<a name="views-and-extensions"></a>
## Views & Extensions

The schema builder can manage raw SQL, database extensions, and views:

```python
Schema.run_sql("UPDATE settings SET value = '1' WHERE key = 'migrated'")
Schema.install_extension("pg_trgm")
Schema.create_view("active_users", "SELECT * FROM users WHERE active")
Schema.create_materialized_view("revenue", "SELECT ...", with_data=True)
Schema.refresh_materialized_view("revenue", concurrently=True)
```

Async introspection helpers — `has_table`, `has_column`, `get_columns`, `has_view` — let a migration branch on the current schema state:

```python
async def up(schema: Schema) -> None:
    if not await schema.has_column("users", "phone"):
        Schema.table("users", lambda t: t.string("phone").nullable())
```

<a name="database-connections"></a>
## Database Connections

Connections read `config/database.py` — `default` picks the active connection and `connections` maps each named connection to its settings. The `DB_*` environment variables are the fallback when a key isn't in the file (see [the cascade](../core-concepts/configuration.md#the-cascade)). Set `DB_CONNECTION` to choose a driver:

| `DB_CONNECTION` | Driver |
|---|---|
| `postgresql` / `postgres` | `postgresql+asyncpg` |
| `mysql` / `mariadb` | `mysql+aiomysql` |
| `sqlite` | `sqlite+aiosqlite` |
| `memory` | in-memory SQLite |

```ini
DB_CONNECTION=postgresql
DB_HOST=127.0.0.1
DB_PORT=5432
DB_DATABASE=myapp
DB_USERNAME=postgres
DB_PASSWORD=secret
```

Alternatively set a full `DB_URL`, which wins over the composed fields. The `DatabaseServiceProvider` binds the engine, session maker, and session into the [container](../core-concepts/service-container.md), and pings the database on boot.

> [!NOTE]
> The database is only wired up when a connection is configured — `DB_URL`/`DB_CONNECTION` set, or a `config/database.py` that supplies a connection. The `DatabaseServiceProvider` is opt-in — add it to `bootstrap/providers.py`. See [Service Providers](../core-concepts/service-providers.md#opt-in-providers).

<a name="seeding"></a>
## Seeding

Seeders populate your database with data — useful for development and tests.

<a name="writing-seeders"></a>
### Writing Seeders

Generate one with `arvel make:seeder`, then implement the async `run` method:

```python
from arvel.database import Seeder
from app.models.user import User


class DatabaseSeeder(Seeder):
    async def run(self) -> None:
        await User.create(name="Ada", email="ada@example.com")
        # run another seeder by awaiting its run()
        await ProductSeeder().run()
```

Seeders pair naturally with [factories](#factories) for bulk fake data:

```python
class DatabaseSeeder(Seeder):
    async def run(self) -> None:
        await UserFactory().count(50).create()
        await UserFactory().has("posts", PostFactory(), count=3).count(10).create()
```

> [!WARNING]
> Don't call `session.commit()` inside a seeder — the `db:seed` runner owns the transaction and commits after `run()` returns. Also note that `self.call(other_seeder)` is a composition helper that returns the seeder unchanged; it does **not** execute it. To run another seeder, await its `run()` directly.

> [!NOTE]
> The default `DatabaseSeeder` refuses to run when `app.env` is `production`. Custom seeders run regardless of environment, so guard your own destructive seeders if needed.

<a name="running-seeders"></a>
### Running Seeders

```bash
arvel db:seed                      # runs DatabaseSeeder
arvel db:seed --seeder ProductSeeder
```

<a name="factories"></a>
## Factories

Factories generate model instances for tests and seeding, with sensible fake data. Define a `Factory` subclass with a `definition` that returns the default attributes. Generate one with `arvel make:factory`:

```python
from typing import Any
from arvel.database import Factory
from app.models.user import User


class UserFactory(Factory[User]):
    model = User

    def definition(self) -> dict[str, Any]:
        return {"name": "Ada Lovelace", "email": "ada@example.com"}
```

Make instances (in memory) or create them (persisted):

```python
user = await UserFactory().create()
users = await UserFactory().count(3).create()
admin = await UserFactory().state({"is_admin": True}).create()
draft = UserFactory().make()           # not persisted
```

<a name="unique-and-sequenced-data"></a>
### Unique & Sequenced Data

A fixed `definition` produces duplicate emails when you create many rows. Give each instance a distinct value with `sequence`, which calls a function with an incrementing counter, or read the per-factory counter directly with `seq`:

```python
users = await (
    UserFactory()
    .count(3)
    .sequence("email", lambda n: f"user{n}@example.com")
    .create()
)
# user1@…, user2@…, user3@…
```

`state` also accepts a **callable** when the override needs to be computed per build:

```python
await UserFactory().count(5).state(lambda: {"token": secrets.token_hex(8)}).create()
```

<a name="factory-relationships"></a>
### Relationships

Build relationships, attach pivots, and run callbacks:

```python
author = await UserFactory().has("posts", PostFactory(), count=3).create()
post = await PostFactory().for_("author", author).create()

await UserFactory().has_attached(
    "roles", RoleFactory(), count=2, pivot={"assigned_by": "system"}
).create()

await UserFactory().after_creating(lambda u, faker: notify(u)).create()
```

<a name="factory-states-and-connections"></a>
### Trashed Rows, Quiet Builds & Connections

A few modifiers cover the less common cases:

```python
await PostFactory().count(5).trashed().create()        # rows start soft-deleted
await UserFactory().count(10).create_quietly()         # skip lifecycle events
await UserFactory().connection("analytics").create()   # persist on a named connection
```

`trashed()` requires the model to use [`SoftDeletes`](models.md#soft-deleting); it raises otherwise.

> [!NOTE]
> Faker is an optional dependency. When installed, it's passed as the second argument to `after_making` / `after_creating` callbacks. Without it, those callbacks receive `None` for the faker.
