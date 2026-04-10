# Soft Deletes

Not every delete should vanish from disk. **Soft deletes** mark rows with a `deleted_at` timestamp instead of issuing `DELETE`, so you can restore mistakes, audit history, or respect foreign-key constraints that prefer a living row.

In Arvel, mix `SoftDeletes` into your model and the framework handles the rest: repositories soft-delete by default, queries hide trashed rows automatically, and the query builder exposes Laravel-familiar escape hatches.

## Adding the mixin

```python
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from arvel.data import ArvelModel
from arvel.data.soft_deletes import SoftDeletes


class Post(SoftDeletes, ArvelModel):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
```

`SoftDeletes` declares `deleted_at: Mapped[datetime | None]` and registers a global scope that filters to `deleted_at IS NULL` for ordinary reads.

## Querying trashed rows

The query builder mirrors Eloquent’s vocabulary:

```python
# Include trashed rows in the result set
await Post.query(session).with_trashed().all()

# Only soft-deleted rows
await Post.query(session).only_trashed().all()
```

Under the hood these manipulate the `SoftDeleteScope` global scope — the same mechanism other global scopes use, so behavior stays consistent.

## Deleting and restoring

Repositories detect the mixin: `delete()` sets `deleted_at` instead of removing the row. Dedicated restore flows (when you implement them) go through observer hooks like `restoring` / `restored` if you need side effects.

## The `trashed` property

Each instance exposes `trashed` — `True` when `deleted_at` is not `None`. Useful in serializers or policies without re-querying.

## Migrations

Add `deleted_at` in a migration — nullable `DateTime(timezone=True)` — when you introduce the mixin. Existing rows simply have `NULL` and behave as "not deleted."

Soft deletes are a contract with your future self: users get undo, operators get auditability, and your code keeps a single obvious path for "this row counts" versus "this row is gone."
