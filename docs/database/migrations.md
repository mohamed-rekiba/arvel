# Migrations & Schema

A migration is version control for your database schema. Instead of hand-editing tables and hoping
every environment matches, you describe each change as a small Python class with an `up` (apply) and a
`down` (revert), commit it, and every machine runs the same ordered set of changes to arrive at the
same schema. arvel's migrations run on Alembic under the hood but you write against a fluent schema
builder that renders correct DDL for **PostgreSQL, MySQL, and SQLite** from one definition.

## Your first migration

Generate a migration with the CLI. A name of the form `create_<table>_table` scaffolds a create/drop
stub for you:

```bash
arvel make:migration create_posts_table
# → database/migrations/2026_07_08_120000_create_posts_table.py
```

That gives you a `Migration` subclass with a `define(t)` blueprint. Fill in the columns:

```python
from arvel.database import Migration


class CreatePostsTable(Migration):
    def up(self, schema):
        def define(t):
            t.id()
            t.foreign_id("user_id")
            t.string("title")
            t.text("body")
            t.boolean("published").default(False)
            t.timestamps()

        schema.create("posts", define)

    def down(self, schema):
        schema.drop("posts")
```

Then apply it — and roll it back if you need to:

```bash
arvel migrate                  # apply every pending migration, in order
arvel migrate:rollback         # undo the last batch
```

`schema.create(name, define)` builds a new table from the blueprint; `schema.table(name, define)`
**adds** columns to an existing one; `schema.drop(name)` drops it. Any name that *isn't*
`create_<table>_table` (e.g. `add_slug_to_posts`) scaffolds a generic `up`/`down` stub instead.

## The column builder

Inside `define(t)`, declare columns with the blueprint `t`:

```python
t.id()
t.foreign_id("user_id")
t.string("title")
t.text("body")
t.medium_text("summary")
t.long_text("content")
t.char("code", 8)
t.integer("views").default(0)
t.unsigned_integer("count")                   # also unsigned_big/small/tiny_integer
t.boolean("published").default(False);
t.timestamps()
t.timestamp("published_at").nullable()        # DateTime — .not_null() is the explicit inverse
t.soft_deletes()                              # nullable deleted_at — the SoftDeletes column
t.unique_index("email")                       # named-or-derived unique index (multi-column ok)
```

Cross-dialect types render natively where it matters (real `UNSIGNED` / `LONGTEXT` / `MEDIUMTEXT`
on MySQL; portable equivalents elsewhere), so a ported migration runs unchanged.

A model's own `__fields__` follow the same convention: a `str` field becomes `VARCHAR(255)` and a
`datetime` field a real timezone-aware `DateTime` — so the table is valid DDL on **every** dialect,
including MySQL (which rejects a length-less `VARCHAR`). For a longer column declare the type
explicitly, e.g. `__fields__ = {"body": sa.Text()}`.


## Soft deletes, ids, pruning

```python
from arvel.database import SoftDeletes, HasUuids, Prunable

class Post(Model, SoftDeletes):    # delete() sets deleted_at; default queries hide trashed
    ...

await post.delete()                # soft
await Post.with_trashed().get()
await post.restore()

class Token(Model, HasUuids): ...  # string UUIDv7 primary key (HasUlids for ULIDs)

class Session(Model, Prunable):
    @classmethod
    def prunable(cls): return cls.where_null("user_id")
await Session.prune()              # delete prunable() rows (pair with schedule:run)
```

## Evolving a table

`Schema` (the object your migration's `up`/`down` receive) also modifies an *existing* table —
`rename_column`/`change_column`/`drop_foreign`/`drop_index`/`drop_unique`/`rename`, over Alembic:

```python
def up(self, schema):
    schema.rename_column("posts", "body", "content")
    schema.change_column("posts", "views", nullable=True, default=0)   # type/nullable/default/comment
    schema.rename("posts", "articles")
    schema.drop_foreign("comments", "comments_post_id_fkey")
    schema.drop_unique("users", "users_email_key")
    schema.drop_index("posts", "ix_posts_slug")

def down(self, schema):
    schema.rename_column("posts", "content", "body")
    ...
```

### Conditional & idempotent steps

`has_table(name)` and `has_column(table, column)` let a migration branch on what's actually there,
and `drop_if_exists(name)` drops a table only when it exists (plain `drop` raises on a missing one).
Each reads the live schema fresh, so a check right after a `create` in the same migration sees the
new table:

```python
def up(self, schema):
    if not schema.has_table("settings"):
        schema.create("settings", lambda t: (t.id(), t.string("key"), t.json("value")))
    if not schema.has_column("users", "timezone"):
        schema.table("users", lambda t: t.string("timezone").nullable())
    schema.drop_if_exists("legacy_sessions")   # no-op if it was never there
```

`change_column`'s kwargs (`type=`, `nullable=`, `default=`, `comment=`) are independent — pass only
the ones you're changing. **SQLite** has no in-place `ALTER COLUMN`/`DROP CONSTRAINT`, so
`rename_column`/`change_column`/`drop_foreign`/`drop_unique` route through Alembic's
`batch_alter_table` there (it recreates the table under the hood) — the same migration code runs
unchanged on every dialect.

`drop_index`/`rename` (a table rename) are native everywhere, no batch
mode needed. A constraint's name (for `drop_foreign`/`drop_unique`) is whatever the database
assigned it (e.g. Postgres's `<table>_<column>_fkey`/`_key` defaults) — inspect the table
(`\d <table>` / `Inspector.get_foreign_keys`) if you didn't name it explicitly.

`Migrator.drop_all()` reflects and drops **every** table (views first on Postgres, with CASCADE)
— it is what `db:wipe` and `migrate:fresh` run; reach for the commands, not the method, outside
of harness code.

## migrate:refresh / migrate:fresh

```
arvel migrate:fresh            # drop every table, then re-run every migration
arvel migrate:refresh          # roll back every migration, then re-run them
arvel migrate:refresh --seed   # ...then run the app's bound seeder
```

## Seeding

Populate tables with a `Seeder` and `arvel db:seed` — see [Seeding](seeding.md).

## Common mistakes & gotchas

- **Editing an applied migration instead of adding a new one.** Once a migration has run somewhere,
  change the schema with a *new* migration — editing the old file won't re-run on machines that
  already applied it.
- **No `down`.** A migration without a working `down` can't be rolled back — `migrate:rollback` and
  `migrate:refresh` depend on it. Make `down` the exact inverse of `up`.
- **`schema.table` for a column change.** `schema.table(name, define)` only *adds* columns. To
  rename, retype, or drop, use `rename_column`/`change_column`/`drop_column` (or `execute` for
  anything they don't cover).
- **A length-less string on MySQL.** A bare `str` field renders `VARCHAR(255)`; MySQL rejects a
  `VARCHAR` with no length, so declare `sa.Text()` explicitly for long columns.
- **`migrate:fresh` on production.** It drops every table. It's a development/testing convenience —
  never point it at data you care about.

## How it works

Each `Migration` subclass records its `name` (the file stem) in a migrations table; `migrate` applies
the ones not yet recorded, in filename (timestamp) order, and `migrate:rollback` reverses the last
batch by calling `down`. The `Schema` object wraps an Alembic `Operations` instance, so every builder
call compiles to real DDL for the active dialect — and the Postgres-only features degrade with a
warning (see [SQL Views & Functions](sql-views.md)) rather than crashing a sqlite/mysql run.

## See also

- [Casts & Serialization](casts.md) — how a column's stored type maps to a Python type.
- [Factories](factories.md) · [Console](../console.md) — seeding, and the `migrate*`/`db:seed` commands.
- [SQL Views & Functions](sql-views.md) — creating views, materialized views, and functions in a migration.
- [Relationships](relationships.md) — the foreign keys `t.foreign_id`/`t.morphs` set up.
