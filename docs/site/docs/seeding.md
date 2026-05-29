# Seeding

Seeders populate your database with test or example data. Use them for:

- Bootstrapping a development environment with realistic data
- Loading reference data (countries, currencies, default roles)
- Setting up reproducible state for integration tests

## Defining a seeder

```bash
uv run arvel make:seeder UserSeeder
```

```python
# database/seeders/user_seeder.py
from arvel.database import Seeder

from app.models import User


class UserSeeder(Seeder):
    async def run(self) -> None:
        await User.create(name="Alice", email="alice@example.com")
        await User.create(name="Bob", email="bob@example.com")
```

## Running seeders

```bash
# Run the default seeder (DatabaseSeeder)
uv run arvel db:seed

# Run a specific seeder
uv run arvel db:seed --seeder UserSeeder
```

The `--seeder` value must match a class name in `database/seeders/<snake_case>.py`. Names are restricted to `^[A-Za-z][A-Za-z0-9_]*$` so they map cleanly to filenames and can't escape the seeders directory.

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Seeder ran successfully |
| `1` | Seeder's `run()` raised |
| `2` | Bootstrap failure, file missing, class missing, or invalid `--seeder` name |

## The default seeder

Create `database/seeders/database_seeder.py` to compose all your seeders:

```python
from arvel.database import Seeder
from database.seeders.user_seeder import UserSeeder
from database.seeders.role_seeder import RoleSeeder


class DatabaseSeeder(Seeder):
    async def run(self) -> None:
        await self.call(RoleSeeder)
        await self.call(UserSeeder)
```

`db:seed` runs this class by default. Each `self.call(...)` resolves the seeder via the container and invokes its `run()`.

## Using factories

For bulk fake data, factories work hand-in-hand with seeders:

```python
class UserSeeder(Seeder):
    async def run(self) -> None:
        await UserFactory().count(20).create()
        await UserFactory().state({"role": "admin"}).count(2).create()
```

See [Factories](arvent-factories.md) for the factory API.

## Idempotency

Seeders should be safe to run repeatedly. The common patterns:

```python
# Skip if already seeded
if await User.exists():
    return

# Upsert by a unique field
await User.upsert(
    [{"email": "alice@example.com", "name": "Alice"}],
    unique_by=["email"],
    update=["name"],
)
```

## Production caution

Seeders are typically for development. If you do run them in production (e.g. to load reference data), name a dedicated reference-data seeder explicitly rather than running the default `DatabaseSeeder` (which may include fake data):

```bash
APP_ENV=production uv run arvel db:seed --seeder ReferenceDataSeeder
```

`db:seed` doesn't ship an environment guard yet, so the responsibility for not running a fake-data seeder in production is on the operator. Make destructive seeders idempotent and obvious about their scope.

## Where to next?

- [Migrations](migrations.md) — schema management.
- [Factories](arvent-factories.md) — generating test data.
- [Testing → Database](database-testing.md) — per-test seeding patterns.
