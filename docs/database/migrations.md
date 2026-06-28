# Migrations & Schema

In a migration's blueprint, declare columns with the Laravel-style builder:

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
on MySQL; portable equivalents elsewhere), so a ported Laravel migration runs unchanged.


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

