# Migrations

Migrations are version control for your database schema. Each migration captures one logical schema change — creating a table, adding a column, dropping an index — and ships with both an `up()` (apply) and a `down()` (revert) method.

Arvel's migration DSL is the Laravel `Schema::create(...)` API translated to Python. It compiles to SQLAlchemy `Table` objects, which Alembic then diffs and applies — so you get the high-level DSL ergonomics with Alembic's autogenerate machinery underneath.

## Creating a migration

```bash
# Table migration (default)
uv run arvel make:migration create_posts_table

# View migration
uv run arvel make:migration --view create_active_users_view

# PostgreSQL extension migration
uv run arvel make:migration --extension install_uuid-ossp_extension

# Materialized view migration (PostgreSQL only)
uv run arvel make:migration --materialized-view create_daily_stats_view
```

`--view`, `--materialized-view`, and `--extension` are mutually exclusive. Each flag generates a different stub — see [Views](#views), [Materialized views](#materialized-views-postgresql), and [Extensions](#extensions-postgresql) below.

The default (table migration) generates a timestamped file under `database/migrations/`:

```python
# database/migrations/2026_05_19_020000_create_posts_table.py
"""create_posts_table."""

from arvel.database import Blueprint, Schema


async def up(schema: Schema) -> None:
    def build(t: Blueprint) -> None:
        t.id()
        t.string("title", length=200)
        t.text("body")
        t.foreign_id("user_id").constrained().cascade_on_delete()
        t.boolean("published").default(False)
        t.timestamps()
        t.soft_deletes()

    Schema.create("posts", build)


async def down(schema: Schema) -> None:
    Schema.drop("posts")
```

Each migration is a module with two coroutines: `up()` applies the change and `down()` reverts it. The `schema` parameter is the `Schema` facade — passed in for explicit-over-implicit, even though it's identical to the imported one.

## The schema builder

The callback receives a `Blueprint` (`t`) with column-builder methods:

```python
t.id()                              # auto-incrementing primary key
t.uuid("id").primary()              # UUID primary key
t.string("name", length=120)        # VARCHAR(120)
t.text("body")                      # TEXT
t.long_text("body")                 # CLOB / TEXT for very long values
t.integer("count")
t.big_integer("total_cents")
t.decimal("amount", precision=10, scale=2)
t.boolean("active")
t.date("birthday")
t.datetime("starts_at")
t.timestamp("recorded_at")
t.json("metadata")
t.jsonb("metadata")            # PostgreSQL JSONB (degrades to JSON elsewhere)
t.enum("status", ("draft", "published", "archived"))
t.foreign_id("user_id")             # bigint + FK helper
```

Each column builder is chainable:

```python
t.string("email", length=180).unique().not_null()
t.text("bio").nullable()
t.integer("score").default(0)
t.jsonb("settings").nullable(value=False).server_default("'{}'::jsonb")
```

For foreign keys:

```python
t.foreign_id("user_id").constrained()                       # FK to users.id
t.foreign_id("user_id").constrained("users")                # explicit table
t.foreign_id("user_id").constrained().cascade_on_delete()
t.foreign_id("user_id").constrained().restrict_on_delete()
```

For indexes and unique constraints:

```python
t.index(["author_id", "published"])         # plain B-tree index
t.index(["deleted_at"], name="...",
        where="deleted_at IS NULL")          # partial index (see below)
t.index(["user_id"], name="...",
        unique=True,
        where="status = 'pending'")          # partial unique index
t.unique(["email"])                          # unique constraint
t.unique(["slug"], name="...",
         nulls_not_distinct=True)            # UNIQUE NULLS NOT DISTINCT (PG 15+)
t.fulltext(["title", "body"])               # GIN full-text (see below)
t.expression_index(                          # functional / expression index
    "(slug->>'en')",
    name="posts_slug_en_unique",
    unique=True,
)
```

For Arvel's first-party patterns:

```python
t.timestamps()                       # created_at + updated_at
t.soft_deletes()                     # deleted_at
t.morphs("commentable")              # commentable_id + commentable_type (polymorphic)
```

### Partial indexes

A partial index only covers rows that match a `WHERE` predicate. For the most common use case — soft-deleted tables — this keeps the index small and ensures the query planner picks it for active-record queries.

#### `soft_deletes()` auto-index (default)

`t.soft_deletes()` automatically creates a `WHERE deleted_at IS NULL` partial index. You don't need to add it manually:

```python
from arvel.database import Blueprint, Schema


async def up(schema: Schema) -> None:
    def build(t: Blueprint) -> None:
        t.id()
        t.string("category")
        t.soft_deletes()
        # ↑ Creates the deleted_at column AND an ix_posts_deleted_at_active
        #   partial index (WHERE deleted_at IS NULL) automatically.

    schema.create("posts", build)
```

The generated index name follows the pattern `ix_{table}_{column}_active`. Pass `index=False` to skip it when you prefer to manage the index yourself (e.g. if you only need a composite partial index):

```python
t.soft_deletes(index=False)
# composite index covers the single-column case implicitly
t.index(
    ["category", "deleted_at"],
    name="posts_category_active_idx",
    where="deleted_at IS NULL",
)
```

#### Custom partial indexes with `where=`

Pass `where=` as a plain SQL string for any other partial index:

```python
t.index(
    ["category", "deleted_at"],
    name="posts_category_active_idx",
    where="deleted_at IS NULL",
)
```

Blueprint wraps the string in a SQLAlchemy `text()` clause automatically. If you already have a `text()` or column expression you can pass it directly — both forms are accepted.

`where=None` (the default) produces a plain B-tree index — identical to omitting the parameter entirely.

On dialects that don't support partial indexes, Alembic raises its own error at migration time. Arvel doesn't suppress it.

#### Partial unique indexes

Combine `unique=True` with `where=` to enforce uniqueness only within a filtered subset — for example, one pending order per user, but allow multiple completed ones:

```python
t.index(
    ["user_id"],
    name="one_pending_per_user",
    unique=True,
    where="status = 'pending'",
)
```

When you need uniqueness on a full set of rows without a predicate, use `t.unique(...)` instead — it issues a `UNIQUE` constraint, which is semantically clearer.

### NULLS NOT DISTINCT (PostgreSQL 15+)

By default, PostgreSQL's `UNIQUE` constraint treats `NULL` as not equal to itself — so a column can have multiple `NULL` rows and still satisfy the constraint. Use `nulls_not_distinct=True` when you want `NULL` to be treated as a real value for uniqueness purposes (e.g. an optional `slug` that must still be unique when set):

```python
t.unique(
    ["slug"],
    name="posts_slug_uq",
    nulls_not_distinct=True,   # UNIQUE NULLS NOT DISTINCT
)
```

`nulls_not_distinct=False` makes the `NULLS DISTINCT` behaviour explicit in the DDL. `nulls_not_distinct=None` (the default) omits the clause entirely — identical to the current behaviour on every supported database.

This is a PostgreSQL 15+ feature (SQLAlchemy renders it automatically). On older PostgreSQL versions the database raises a syntax error at migration time — Arvel doesn't polyfill it.

### Expression indexes (PostgreSQL)

`t.index()` and `t.unique()` only accept plain column names. When you need an index on a computed value — a JSONB path, a lowercased string, a cast — use `t.expression_index()`:

```python
# Unique index on the English slug extracted from a JSONB column
t.expression_index(
    "(slug->>'en')",
    name="posts_slug_en_unique",
    unique=True,
)

# Non-unique index on a lowercased email
t.expression_index(
    "lower(email)",
    name="users_email_lower_idx",
)
```

The expression is passed verbatim to `CREATE INDEX … ON t (expr)`, so any PostgreSQL expression that's valid in that position works. Pass `unique=True` for a `UNIQUE` expression index.

### Server-side defaults

`.server_default(sql)` sets a default evaluated by the database on `INSERT`, as opposed to `.default(value)` which is applied by the Python layer.

Pass any SQL fragment as a string — it's wrapped in `text()` automatically:

```python
t.jsonb("config").nullable(value=False).server_default("'{}'::jsonb")
t.integer("version").nullable(value=False).server_default("1")
t.timestamp("expires_at").server_default("NOW() + INTERVAL '30 days'")
```

You can also pass a SQLAlchemy expression directly (e.g. `func.now()`) when you need something more structured — `.use_current()` is a convenience wrapper that does exactly this for `CURRENT_TIMESTAMP`.

### Escape hatch: `raw_column`

Some dialect features don't have a place in the DSL — PostgreSQL generated/computed columns, exotic check constraints. Hand-build a `sqlalchemy.Column` and pass it through verbatim with `t.raw_column(...)`:

```python
from sqlalchemy import Column, Computed, Integer

def build(t: Blueprint) -> None:
    t.id()
    t.integer("price_cents")
    t.integer("quantity")
    t.raw_column(
        Column("total_cents", Integer, Computed("price_cents * quantity", persisted=True))
    )
```

`raw_column` short-circuits the DSL — chain modifiers (`nullable()`, `unique()`, `default()`) are deliberately ignored, because you own the column wholesale. Reach for it only when nothing else fits. Server-side defaults specifically don't require it — use `.server_default()` instead.

### Email columns

Emails are plain VARCHAR (see [ADR-077](https://github.com/your-org/arvel/blob/main/docs/adr/ADR-077-email-validation-at-boundary.md)). Validation lives on the Pydantic boundary schemas via `EmailStr`, not on the column. The migration call is the standard `string` helper with `.unique()`:

```python
def build(t: Blueprint) -> None:
    t.id()
    t.string("name", 255)
    t.string("email", 254).unique()
    t.timestamps()
```

`UNIQUE` already implies a unique B-tree index on every supported dialect, so no separate `.index()` is needed. Length `254` is the practical RFC-5321 max.

## Modifying tables

```python
"""add_slug_to_posts."""

from arvel.database import Blueprint, Schema


async def up(schema: Schema) -> None:
    def change(t: Blueprint) -> None:
        t.string("slug", length=200).after("title").unique()

    Schema.table("posts", change)


async def down(schema: Schema) -> None:
    def change(t: Blueprint) -> None:
        t.drop_column("slug")

    Schema.table("posts", change)
```

`Schema.table(...)` opens an existing table for modification. Use `t.drop_column(...)`, `t.rename_column(...)`, `t.change_column(...)` for the destructive ops.

## Running migrations

```bash
# Apply pending migrations (the first run creates the `migrations` tracking table)
uv run arvel migrate

# See what would run without applying
uv run arvel migrate --dry-run

# Show every migration with applied / pending status + batch + applied_at
uv run arvel migrate:status

# Roll back the most recent *batch* (Laravel semantics — all migrations
# applied by the most recent `migrate` invocation, undone together)
uv run arvel migrate:rollback
```

Each `migrate` run picks the next batch number and tags every migration it applies with that batch. `migrate:rollback` then walks the most recent batch in reverse and calls each migration's `down()` in its own transaction. A failure mid-batch leaves the earlier applied migrations in place — fix the offender, then re-run `migrate` to pick up the rest.

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Success (or nothing to migrate) |
| `1` | A migration body raised — fix the migration and re-run |
| `2` | Bootstrap failure (no Application, no engine, migrations directory missing) |

## Reversibility

Each migration ships with `down()`. The runner doesn't *force* you to write a working `down()` — but `migrate:rollback` will call it, and a no-op `down()` means you can't safely undo the change. Treat `down()` as part of the deliverable, not an afterthought.

## Multi-step migrations

For complex schema changes (e.g. add column, backfill it, then add a NOT NULL constraint), split into multiple migrations:

```bash
uv run arvel make:migration add_email_to_users
uv run arvel make:migration backfill_user_email
uv run arvel make:migration require_user_email
```

This keeps each step small, reversible, and reviewable.

## Production-safe patterns

- **Add columns nullable, then backfill, then add NOT NULL** — running NOT NULL on a populated column rewrites the table.
- **Add indexes concurrently** (Postgres: `CREATE INDEX CONCURRENTLY`). Arvel's `t.index(...).concurrently()` emits the right SQL on Postgres; on other databases it's a no-op modifier.
- **Drop columns in two steps** — first remove all reads (code-only deploy), then drop the column (migration deploy). Avoid the long lock window of "drop and pray".
- **Use partial indexes on soft-deleted tables** — `where="deleted_at IS NULL"` keeps the index to active rows only. On a table with 90% soft-deleted rows this can be an order of magnitude smaller than a full B-tree index on the same column.

## Views

Generate a view migration with `--view`:

```bash
uv run arvel make:migration --view create_active_users_view
```

This produces:

```python
__viewname__ = "active_users"

async def up(schema: Schema) -> None:
    schema.create_view(__viewname__, "SELECT * FROM users WHERE active = 1")

async def down(schema: Schema) -> None:
    schema.drop_view_if_exists(__viewname__)
```

The view name is inferred from the migration name by stripping the verb prefix and `_view` suffix (`CreateActiveUsersView` → `active_users`). Change `__viewname__` in the stub if the inferred name isn't right.

### Schema view methods

```python
Schema.create_view(view_name, select_sql)    # CREATE VIEW … AS …
Schema.drop_view(view_name)                  # DROP VIEW …
Schema.drop_view_if_exists(view_name)        # DROP VIEW IF EXISTS …
await Schema.has_view(engine, "view_name")   # True/False introspection
await Schema.has_view("view_name")           # uses the active session's bind
```

The `SELECT` string is developer-authored in the migration file — treat it with the same care as any other DDL.

Once the view exists in the database, map an ORM model to it with `ViewModel` — see [View models](arvent.md#view-models) in the Arvent guide.

## Materialized views (PostgreSQL)

Materialized views store a query snapshot on disk. They need explicit refreshes to stay current — unlike regular views, which always reflect live data.

Generate a materialized view migration with `--materialized-view`:

```bash
uv run arvel make:migration --materialized-view create_daily_stats_view
```

This produces:

```python
__viewname__ = "daily_stats"

async def up(schema: Schema) -> None:
    schema.create_materialized_view(__viewname__, "SELECT count(*) FROM orders")
    # schema.refresh_materialized_view(__viewname__, concurrently=True)

async def down(schema: Schema) -> None:
    schema.drop_materialized_view_if_exists(__viewname__)
```

### Schema materialized view methods

```python
Schema.create_materialized_view(name, select_sql, with_data=True)
Schema.refresh_materialized_view(name, concurrently=False)
Schema.drop_materialized_view(name)
Schema.drop_materialized_view_if_exists(name)
await Schema.has_materialized_view(engine, "name")
await Schema.has_materialized_view("name")           # active session bind
```

`with_data=False` emits `CREATE MATERIALIZED VIEW … WITH NO DATA` — useful when you want the shell in place before a heavy initial refresh in a follow-up step.

`concurrently=True` on refresh requires a **unique index** on the materialized view (Postgres requirement). Without one, drop the flag or add the index in the same migration before refreshing.

MySQL/MariaDB and SQLite have no materialized-view equivalent — keep these migrations Postgres-only, same as extensions.

### Indexes on views and materialized views

Materialized views don't go through `schema.create()`, so Blueprint isn't available. Use the two `Schema`-level index methods instead:

```python
Schema.create_index(name, table, columns, *, unique=False, using=None)
Schema.create_expression_index(name, table, expression, *, unique=False)
```

`table` can be any relation name — materialized view, regular view, or table. A full example:

```python
async def up(schema: Schema) -> None:
    schema.create_materialized_view("stats", _SELECT_SQL, with_data=False)

    # Required for REFRESH CONCURRENTLY
    schema.create_index("stats_id_unique", "stats", ["id"], unique=True)

    # GIN index for full-text search
    schema.create_index("stats_search_gin", "stats", ["search_vector"], using="gin")

    # Plain column index
    schema.create_index("stats_created_at_idx", "stats", ["created_at"])

    # Descending index (expression form)
    schema.create_expression_index("stats_score_desc_idx", "stats", "score DESC")

    schema.refresh_materialized_view("stats", concurrently=False)
```

These same methods work on regular tables when you need to add an index outside a `schema.create()` or `schema.table()` callback — for example, after creating a view that shadows a table name.

To query a materialized view through the ORM, use `ViewModel` with `__is_materialized_view__ = True` — it exposes `refresh_view()` which delegates to `Schema.refresh_materialized_view`. See [View models](arvent.md#view-models).

## Extensions (PostgreSQL)

Install and uninstall Postgres extensions through migrations with `--extension`:

```bash
uv run arvel make:migration --extension install_uuid-ossp_extension
```

This produces:

```python
__extension__ = "uuid-ossp"

async def up(schema: Schema) -> None:
    schema.install_extension(__extension__)

async def down(schema: Schema) -> None:
    schema.uninstall_extension(__extension__)
```


### Schema extension methods

```python
Schema.install_extension(name)    # CREATE EXTENSION IF NOT EXISTS "name"
Schema.uninstall_extension(name)  # DROP EXTENSION IF EXISTS "name"
```

Extension names are always double-quoted in the emitted DDL, so hyphenated names work once you set the right string. These methods are **PostgreSQL-only** — they will fail at `up()` time on SQLite and MySQL.

## JSONB columns (PostgreSQL)

`t.jsonb(name)` maps to `JSONB` on PostgreSQL and degrades to plain `JSON` on every other dialect (SQLite in CI, MySQL). Your test suite works without a real Postgres instance.

```python
from arvel.database import Blueprint, Schema


async def up(schema: Schema) -> None:
    def change(t: Blueprint) -> None:
        t.jsonb("metadata").nullable()

    Schema.table("products", change)


async def down(schema: Schema) -> None:
    def change(t: Blueprint) -> None:
        t.drop_column("metadata")

    Schema.table("products", change)
```

JSONB supports GIN indexes for containment queries (`@>`, `?`, `?|`, `?&`). Add one with `t.gin_index`:

```python
def change(t: Blueprint) -> None:
    t.jsonb("metadata").nullable()
    t.gin_index(t.table, "metadata")
```

On dialects that emit plain `JSON` (non-Postgres), `gin_index` is a no-op — the column still works, you just lose the PG-specific operator support.

JSONB columns that must default to an empty object or array — common for audit trails, settings bags, and tag lists — use `.server_default()`:

```python
def build(t: Blueprint) -> None:
    t.jsonb("tags").nullable(value=False).server_default("'[]'::jsonb")
    t.jsonb("settings").nullable(value=False).server_default("'{}'::jsonb")
```

The string is passed through `text()` internally, so any valid PostgreSQL expression works.

## Full-text search (PostgreSQL)

Arvel's migration DSL ships two helpers for PostgreSQL full-text search: a `tsvector` column type and a GIN index builder.

### Adding a `tsvector` column

```python
from arvel.database import Blueprint, Schema


async def up(schema: Schema) -> None:
    def change(t: Blueprint) -> None:
        t.tsvector("search_vector").nullable()

    Schema.table("posts", change)


async def down(schema: Schema) -> None:
    def change(t: Blueprint) -> None:
        t.drop_column("search_vector")

    Schema.table("posts", change)
```

`t.tsvector(name)` emits `TSVECTOR` on PostgreSQL. On any other dialect (SQLite in tests, for example) it degrades to `TEXT` — so your test suite runs without a real Postgres instance.

The column is nullable by default, which matches the typical pattern of populating it asynchronously after insert. Add `.not_null()` if your population trigger fires synchronously in the same transaction.

### Adding a GIN index

GIN indexes are what make `@@` searches fast on `tsvector` columns. Add them in the same migration or a separate one:

```python
from arvel.database import Blueprint, Schema


async def up(schema: Schema) -> None:
    def change(t: Blueprint) -> None:
        t.gin_index(t.table, "search_vector")

    Schema.table("posts", change)


async def down(schema: Schema) -> None:
    # GIN indexes are dropped automatically when the table is dropped.
    # For alter-table migrations, drop manually:
    Schema.drop_index("posts", "idx_posts_search_vector_gin")
```

`t.gin_index(table, *cols, name=None)` calls `CREATE INDEX ... USING GIN (col)` internally. The default name follows the pattern `idx_{table}_{col}_gin`. Pass `name="my_idx"` to override.

You can index multiple columns in one call:

```python
t.gin_index(t.table, "title_vector", "body_vector")
# → CREATE INDEX idx_posts_title_vector_body_vector_gin USING GIN (title_vector, body_vector)
```

### Full example

A complete migration for a posts table with FTS support:

```python
"""add_full_text_search_to_posts."""

from arvel.database import Blueprint, Schema


async def up(schema: Schema) -> None:
    def change(t: Blueprint) -> None:
        t.tsvector("search_vector").nullable()
        t.gin_index(t.table, "search_vector")

    Schema.table("posts", change)


async def down(schema: Schema) -> None:
    def change(t: Blueprint) -> None:
        t.drop_column("search_vector")

    Schema.table("posts", change)
```

### Populating the vector

Arvel doesn't handle vector population — that's application-level logic. Common approaches:

**PostgreSQL trigger** (most efficient for write-heavy tables):

```sql
CREATE OR REPLACE FUNCTION posts_search_vector_update() RETURNS trigger AS $$
BEGIN
  NEW.search_vector :=
    setweight(to_tsvector('english', coalesce(NEW.title, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(NEW.body, '')), 'B');
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER posts_search_vector_update
BEFORE INSERT OR UPDATE ON posts
FOR EACH ROW EXECUTE FUNCTION posts_search_vector_update();
```

Put this in a raw `Schema.run_sql(...)` call inside your migration's `up()`:

```python
async def up(schema: Schema) -> None:
    def change(t: Blueprint) -> None:
        t.tsvector("search_vector").nullable()
        t.gin_index(t.table, "search_vector")

    Schema.table("posts", change)
    schema.run_sql("""
        CREATE OR REPLACE FUNCTION posts_search_vector_update() RETURNS trigger AS $$
        BEGIN
          NEW.search_vector :=
            setweight(to_tsvector('english', coalesce(NEW.title, '')), 'A') ||
            setweight(to_tsvector('english', coalesce(NEW.body, '')), 'B');
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER posts_search_vector_update
        BEFORE INSERT OR UPDATE ON posts
        FOR EACH ROW EXECUTE FUNCTION posts_search_vector_update();
    """)
```

**Python on save** (simpler, no trigger required):

```python
from sqlalchemy import func, select

async def before_save(post: Post, session: AsyncSession) -> None:
    post.search_vector = await session.scalar(
        select(
            func.to_tsvector("english", post.title + " " + post.body)
        )
    )
```

**Generated column** (PostgreSQL 12+, if the vector expression is simple enough):

```sql
ALTER TABLE posts
ADD COLUMN search_vector tsvector
GENERATED ALWAYS AS (to_tsvector('english', coalesce(title, '') || ' ' || coalesce(body, '')))
STORED;
```

Use `t.raw_column(...)` to express a generated column in a migration — the DSL doesn't have a dedicated helper for this.

Once your column is populated, query it with `where_full_text` and `order_by_relevance` — see [Query Builder → Full-text search](queries.md#full-text-search-postgresql).

## Where to next?

- [Seeding](seeding.md) — populating tables with example data.
- [ORM](arvent.md) — defining models on top of your schema.
- [Query Builder](queries.md) — querying without models.
