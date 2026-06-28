# Database & ORM

Talking to a database is where most apps spend their plumbing: fetching rows, mapping them to
objects, wiring up relationships, and writing the same CRUD over and over. arvel's ORM collapses
that into the model itself — it's an async **Active-Record**, so a `Post` both *describes* a row and
*is* how you query, save, and relate it. No separate repository layer, no hand-written SQL for the
common cases.

It's built on **SQLAlchemy Core**, so every query the builder emits is a real Core construct that
compiles across **PostgreSQL, MySQL, and SQLite** — you write one expression and it runs on all
three. This page walks from defining a model and basic queries through relationships and scopes to
the advanced Postgres features (JSON, full-text, CTEs, views).

!!! note "Needs a database extra"
    Pick the driver for your database: `uv add 'arvel[postgres]'` (asyncpg), `'arvel[mysql]'`
    (asyncmy), or `'arvel[sqlite]'` (aiosqlite) — each pulls in SQLAlchemy + Alembic.

## Defining a model

```python
from arvel import Model

class Post(Model):
    __fillable__ = ["title", "body", "published"]
    __casts__    = {"published": "bool", "meta": "json"}
    __hidden__   = ["secret"]
    __timestamps__ = True
```

Reading a declared column that hasn't been set yet returns `None` (Laravel parity) — e.g.
`post.body` after `Post.create(title="…")` is `None`, not an error. Accessing a genuinely unknown
attribute still raises `AttributeError`.

### Mass assignment

`create()` and `fill()` only set **mass-assignable** attributes, controlled by two class lists:

- `__fillable__` — an allow-list. If set, only these keys are accepted.
- `__guarded__` — a deny-list (default `["*"]`, i.e. *everything* is guarded). Set `__guarded__ = []`
  to allow every attribute.

A model with **no `__fillable__` and the default `__guarded__ = ["*"]`** is *totally guarded* —
nothing is mass-assignable. Mass-assigning to it raises `MassAssignmentException` rather than silently
dropping the data into an empty row (Laravel parity):

```python
class Account(Model):           # totally guarded — no __fillable__
    __table_name__ = "accounts"

Account().fill({"name": "x"})   # MassAssignmentException: Add [name] to the __fillable__ property …
```

Declare `__fillable__` to opt fields in. A model that *does* set `__fillable__` keeps Laravel's
lenient behavior — an unlisted key is silently ignored (not raised), so passing a request body with
extra fields is safe. `MassAssignmentException` is a programmer error (a missing `__fillable__`), not
user input — it is not a `ValidationException` and renders as a 500, not a 422.


## In this section

- **[Queries](queries.md)** — reading, writing, and reusable scopes.
- **[Relationships](relationships.md)** — has-many / belongs-to / many-to-many, eager loading, aggregates.
- **[Migrations & Schema](migrations.md)** — the schema builder, column types, soft deletes, ids, pruning.
- **[Casts & Serialization](casts.md)** — attribute casts, change tracking, `to_dict`/`to_json`.
- **[Factories](factories.md)** — generate model instances for tests and seeders.
- **[Transactions & Streaming](transactions.md)** — atomic units of work, locks, raw SQL, large-result iteration.
- **[CTEs & Recursive Queries](ctes.md)** — `WITH` / `WITH RECURSIVE` and referential (self-referencing) trees.
- **[SQL Views & Functions](sql-views.md)** — views, materialized views, and stored functions.
- **[JSON, Full-text & Vectors](json-search.md)** — query JSON/JSONB, Postgres full-text, and pgvector columns.

## Common mistakes & gotchas

- **`save()` no-ops when clean.** It only writes when an attribute actually changed (`is_dirty`).
  If a write seems to not happen, check the value really changed.
- **N+1 from lazy relations in a loop.** `for u in users: await u.posts()` fires a query per
  user — use `User.with_("posts")` to batch one `WHERE IN`.
- **Forgetting a global scope is there.** It silently filters every query; use
  `without_global_scope(name)` when you genuinely need the unfiltered set.
- **Mass-assigning an unlisted field.** Only `__fillable__` keys are accepted by `create`/`fill`;
  set anything else explicitly (`post.x = ...`). A model with no `__fillable__` is *totally guarded*
  and raises `MassAssignmentException` instead of silently saving an empty row — declare `__fillable__`.
- **Writing to a `__view__` model.** Read-only models raise `ReadOnlyModelError` on any write
  path (`save`/`delete`/`touch`/`restore`) — that's deliberate; write to the underlying table's
  model instead.
- **Morph column names must match.** `morph_to("commentable")` reads `commentable_id` /
  `commentable_type`; create them with `t.morphs("commentable")` so the names line up.


## How it works

A model's `Builder` composes SQLAlchemy **Core** statement objects — `select()`/`insert()` over
`Table`/`Column` metadata, never raw SQL — so the *same* builder call compiles to PostgreSQL,
MySQL, and SQLite. Relationships resolve in two queries (a `WHERE IN`), avoiding SQL joins;
existence/aggregate helpers compile to correlated subqueries. Migrations run through Alembic on
the write connection; reads can route to a replica with sticky-after-write.


## See also

- [Validation](../validation.md) — `unique`/`exists` rules query the DB.
- [Console](../console.md) — `migrate` / `db:seed`. [Dates & Time](../dates.md) — the `datetime` cast.
