# Getting Started

New to Arvel? Start here. These pages take you from zero to a running API with a model, migration, and query — no prior framework knowledge assumed.

## Recommended path

1. **[Installation](installation.md)** — install the CLI, scaffold a project, generate `APP_KEY`, run the dev server.
2. **[Quickstart](quickstart.md)** — add a model, migration, and two JSON endpoints backed by the database.
3. **[Directory Structure](project-structure.md)** — learn where routes, providers, config, and migrations live.

```bash
uv tool install arvel
arvel new my-app && cd my-app
arvel key:generate
arvel make:model Item -m && arvel migrate
uv run arvel serve --reload
```

## What's in this section

| Page | You'll learn… |
|---|---|
| [Installation](installation.md) | Prerequisites, `arvel new`, optional extras, dev server |
| [Quickstart](quickstart.md) | Routes, models, migrations, ORM queries in handlers |
| [Directory Structure](project-structure.md) | Project layout, boot flow, where to put new code |

## Next

Once the app runs, read [Request Lifecycle](../core-concepts/lifecycle.md) to understand boot order, then [Routing](../the-basics/routing.md) and [Models & CRUD](../orm/models.md) for day-to-day work.
