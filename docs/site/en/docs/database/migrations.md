# Migrations

Schema changes deserve version control. Arvel wraps **Alembic** in a way that feels familiar if you have used Laravel migrations: files live under `database/migrations/`, you generate stubs from the CLI, and you run upgrades and rollbacks with short commands.

Behind the scenes the runner picks async or sync engines based on your URL, and framework packages can even publish bundled migrations into your app when you ask for them.

## Creating a migration

Scaffold a new file with the maker command — it picks up your configured database URL and writes the next revision into your migrations directory:

```bash
arvel make migration create_posts_table
```

Open the generated module and author `upgrade()` and `downgrade()` using Arvel’s **Schema** and **Blueprint** facades. They wrap Alembic operations in a fluent, Laravel-shaped API so you rarely import `op` directly.

```python
from arvel.data import Schema, Blueprint


def upgrade() -> None:
    def _posts(table: Blueprint) -> None:
        table.id()
        table.string("title")
        table.text("body").nullable()
        table.timestamps()

    Schema.create("posts", _posts)


def downgrade() -> None:
    Schema.drop("posts")
```

`Blueprint` covers common column types, indexes, foreign keys with `on_delete` / `on_update`, and Laravel-style `timestamps()`.

## Running migrations

Apply everything pending up to `head`:

```bash
arvel db migrate
```

Target a specific revision if you need to replay history in a controlled way:

```bash
arvel db migrate --revision <revision_id>
```

Production deployments should use the same commands in CI/CD; `--force` exists for environments that identify as production when you intentionally mean it.

## Rolling back

Step backward one revision (or more):

```bash
arvel db rollback --steps 1
```

Always implement `downgrade()` with the same care as `upgrade()`. Alembic only knows how to reverse what you have written.

## Refreshing the database

During local development, sometimes you want a clean slate:

```bash
arvel db fresh
```

That drops tables and reapplies all migrations — destructive by design, and guarded in production unless you pass `--force`.

## Status and visibility

See which revisions exist on disk:

```bash
arvel db status
```

## Publishing framework migrations

Optional tables from Arvel itself (auth, media, notifications, audit, and others) register with the migration system. Copy them into your project with:

```bash
arvel db publish
```

Use `--force` to overwrite files you have already published when the framework ships an updated stub.

## Metadata and models

The environment template wires Alembic to `ArvelModel.metadata`, so new models participate in autogenerate workflows if you adopt them. Even when you hand-write migrations, keeping models and revisions in sync is the same discipline you would expect from any mature SQLAlchemy project — Arvel just gives you the commands and the friendly `Schema` surface to do it quickly.
