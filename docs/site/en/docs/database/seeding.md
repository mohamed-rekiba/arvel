# Seeding

Migrations shape the empty database; **seeders** fill it with life. Arvel’s seeding story mirrors Laravel: subclass `Seeder`, implement `run()`, drop files under `database/seeders/`, and let the CLI discover them in alphabetical order.

Seeders run inside a transaction, with an async session and a `Transaction` facade that exposes typed repositories — so you stay at the same abstraction level as the rest of your app.

## The Seeder class

Every seeder is an async class with one contract: `run(self, tx: Transaction)`.

```python
from arvel.data.seeder import Seeder


class UserSeeder(Seeder):
    async def run(self, tx) -> None:
        await tx.users.create({"name": "Admin", "email": "admin@example.com"})
```

Use repositories on the transaction (`tx.users`, `tx.posts`, …) so observers fire and mass-assignment rules stay enforced.

## Generating a stub

Scaffold a file and class in one step:

```bash
arvel make seeder UserSeeder
```

The command ensures `database/seeders/` exists and drops in a ready-to-fill `Seeder` subclass.

## Running seeders

Execute everything Arvel can import from the seeders directory:

```bash
arvel db seed
```

Run a single class when you want a focused import:

```bash
arvel db seed --class UserSeeder
```

By default, seeding **refuses to run in production** unless you pass `--force`. That guardrail exists because seeders often create admin users or demo data you do not want to accidentally duplicate in a live cluster.

## How execution works

`SeedRunner` builds an async engine from your `DatabaseSettings`, opens a connection, begins a transaction, and constructs a `Transaction` with an `ObserverRegistry`. Each seeder runs inside that unit of work; the transaction commits when the seeder finishes successfully.

If a module fails to import (syntax error, missing dependency), it is skipped with a logged debug message so one broken file does not mask everything else — fix the error and rerun.

## Designing good seeders

Keep seeders **idempotent** when you can: upsert or check before insert so running `arvel db seed` twice does not explode. For local-only demo data, truncating in `down` migrations is rarely the answer — prefer explicit guards or separate "dev" seeders you never ship to production.

Seeding closes the loop between migrations and a pleasant developer experience: migrate, seed, and you have a working app in seconds.
