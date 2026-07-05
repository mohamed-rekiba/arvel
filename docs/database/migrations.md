# Migrations & Schema

In a migration's blueprint, declare columns with the builder:

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
t.timestamp("published_at").nullable()        # DateTime
```

Cross-dialect types render natively where it matters (real `UNSIGNED` / `LONGTEXT` / `MEDIUMTEXT`
on MySQL; portable equivalents elsewhere), so a ported migration runs unchanged.

A model's own `__fields__` follow the same convention: a `str` field becomes `VARCHAR(255)`
 and a `datetime` field a real timezone-aware `DateTime` — so the
table is valid DDL on **every** dialect, including MySQL (which rejects a length-less `VARCHAR`). For
a longer column declare the type explicitly, e.g. `__fields__ = {"body": sa.Text()}`.


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
`renameColumn`/`change`/`dropForeign`/`dropIndex`/`dropUnique`/`rename`, over Alembic:

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

`change_column`'s kwargs (`type=`, `nullable=`, `default=`, `comment=`) are independent — pass only
the ones you're changing. **SQLite** has no in-place `ALTER COLUMN`/`DROP CONSTRAINT`, so
`rename_column`/`change_column`/`drop_foreign`/`drop_unique` route through Alembic's
`batch_alter_table` there (it recreates the table under the hood) — the same migration code runs
unchanged on every dialect. `drop_index`/`rename` (a table rename) are native everywhere, no batch
mode needed. A constraint's name (for `drop_foreign`/`drop_unique`) is whatever the database
assigned it (e.g. Postgres's `<table>_<column>_fkey`/`_key` defaults) — inspect the table
(`\d <table>` / `Inspector.get_foreign_keys`) if you didn't name it explicitly.

## migrate:refresh / migrate:fresh

```
arvel migrate:fresh            # drop every table, then re-run every migration
arvel migrate:refresh          # roll back every migration, then re-run them
arvel migrate:refresh --seed   # ...then run the app's bound seeder
```

## Seeders

```python
from arvel.database import Seeder, WithoutModelEvents

class DatabaseSeeder(Seeder):
    async def run(self) -> None:
        await self.call_once(RolesSeeder)   # RolesSeeder.run() only once per process, however
        await self.call(UsersSeeder)        # many seeders `call_once(RolesSeeder)` themselves
        with WithoutModelEvents():          # bulk-insert without firing creating/created/saved
            await UserFactory().count(1000).create()
```
