# Seeding

Seeders populate your database with data — a set of default roles, demo content for a fresh clone,
reference tables. A seeder is a class with an async `run()` method; you have the full ORM available
inside it.

## Writing seeders

Seeders live in `database/seeders/`. Subclass `Seeder` and implement `run()`:

```python
# database/seeders/database_seeder.py
from arvel.database import Seeder
from app.models.user import User

class DatabaseSeeder(Seeder):
    async def run(self) -> None:
        await User.create(name="Ada", email="ada@example.com")
```

Generate one with `arvel make:seeder`.

## Calling other seeders

Keep seeders focused and compose them from a root seeder with `call()`:

```python
class DatabaseSeeder(Seeder):
    async def run(self) -> None:
        await self.call(RoleSeeder, UserSeeder, ProductSeeder)
```

When several seeders depend on the same shared data (a roles table, say), `call_once()` runs a
seeder **at most once per process** no matter how many times it's reached:

```python
await self.call_once(RoleSeeder)     # runs the first time; a no-op on later calls this run
```

## Running seeders

The root seeder is bound as `"seeder"` in your app. Run it with:

```bash
arvel db:seed
arvel db:seed --force               # skip the confirmation prompt (e.g. in CI / production)
```

`db:seed` runs the app's root seeder, which fans out through your `call()`/`call_once()` tree.

## Progress output

A long seed (downloading images, generating thousands of rows) shouldn't run silently. Each seeder
carries an `output` handle the `db:seed` runner injects — print section headers and wrap slow loops
in a progress bar:

```python
class ProductSeeder(Seeder):
    async def run(self) -> None:
        self.line("Seeding products…")
        for row in self.with_progress_bar(rows):
            await Product.create(**row)
```

Child seeders started via `call()`/`call_once()` inherit the same output handle, so progress reads
consistently across the whole tree. Outside `db:seed` (e.g. calling a seeder from a test) the
handle is a silent no-op, so the same code runs quietly.

## See also

- [Factories](factories.md) — generate model instances with fake data (pairs naturally with
  seeders for volume).
- [Migrations](migrations.md) — shape the schema the seeders fill.
