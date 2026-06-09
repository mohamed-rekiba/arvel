# Quickstart

<a name="introduction"></a>
## Introduction

Let's build a small JSON API: a route, a model, a migration, and an ORM-backed endpoint. This assumes you've [installed Arvel](installation.md) and run `arvel new my-app`.

By the end you'll expose `GET /api/items` and `GET /api/items/{item_id}`, both backed by a database table.

<a name="defining-a-route"></a>
## Defining a Route

A fresh project ships with one route in `routes/api.py`:

```python
from arvel import Route


@Route.get("/api/healthz", name="api.healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
```

Every route handler is a plain `async def`. Add more with `@Route.get`, `@Route.post`, and friends. See [Routing](../the-basics/routing.md).

<a name="creating-a-model-and-migration"></a>
## Creating a Model & Migration

```bash
arvel make:model Item --migration
```

`--migration` (or `-m`) generates two files: the model at `app/models/item.py` and a timestamped migration at `database/migrations/<timestamp>_create_items_table.py`. (`make:model` accepts other companions too — `--factory`, `--controller`, `--all`, and more.)

Edit the model to declare its columns with the schema helpers:

```python
from decimal import Decimal

from arvel.database import Model, Timestamps, boolean, decimal, id_, string


class Item(Model, Timestamps):
    __tablename__ = "items"

    id: int = id_()
    name: str = string(255)
    price: Decimal = decimal(10, 2)
    is_active: bool = boolean(default=True)
```

Each helper (`id_`, `string`, `decimal`, `boolean`) maps a typed attribute to a database column. `Timestamps` adds `created_at` / `updated_at`. See [Models & CRUD](../orm/models.md).

The generated migration starts with just an `id` and `timestamps()`. Add the remaining columns so the table matches the model:

```python
async def up(schema: Schema) -> None:
    def _table(t: Blueprint) -> None:
        t.id()
        t.string("name", length=255)
        t.decimal("price", precision=10, scale=2)
        t.boolean("is_active").server_default("true")
        t.timestamps()

    schema.create(__tablename__, _table)
```

See [Migrations](../orm/migrations.md) for the full column DSL.

<a name="running-the-migration"></a>
## Running the Migration

Configure a database in `.env`. SQLite needs no server:

```ini
DB_CONNECTION=sqlite
DB_URL=sqlite+aiosqlite:///database/database.sqlite
```

Then apply migrations:

```bash
arvel migrate
```

Check status any time with `arvel migrate:status`. See [Migrations](../orm/migrations.md).

<a name="querying-from-a-route"></a>
## Querying From a Route

Add to `routes/api.py`:

```python
from arvel import Route
from app.models.item import Item


@Route.get("/api/items", name="items.index")
async def index() -> list[dict[str, object]]:
    items = await Item.where(is_active=True).order_by("-created_at").get()
    return [{"id": i.id, "name": i.name, "price": str(i.price)} for i in items]


@Route.get("/api/items/{item_id}", name="items.show")
async def show(item_id: int) -> dict[str, object]:
    item = await Item.find_or_fail(item_id)
    return {"id": item.id, "name": item.name, "price": str(item.price)}
```

- `Item.where(is_active=True)` builds a query; `order_by("-created_at")` sorts descending; `.get()` runs it and returns model instances.
- `Item.find_or_fail(item_id)` loads by primary key and raises `ModelNotFoundError` when the row is missing. The HTTP layer translates that to a 404 automatically.

<a name="running-it"></a>
## Running It

```bash
uv run arvel serve --reload
```

- `GET http://127.0.0.1:8000/api/items` → `[]` until you insert data.
- `GET http://127.0.0.1:8000/docs` → interactive OpenAPI docs.

Verify with curl:

```bash
curl http://127.0.0.1:8000/api/healthz
# {"status": "ok"}
curl http://127.0.0.1:8000/api/items
# []
```

<a name="next-steps"></a>
## Next Steps

- Validate request bodies with [form requests](../the-basics/validation.md).
- Shape responses with [API resources](../the-basics/resources.md).
- Add [authentication](../features/authentication.md).
