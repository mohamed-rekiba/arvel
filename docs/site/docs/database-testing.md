# Database Tests

The framework ships two complementary strategies for keeping database state clean across tests: **per-test transactions** and **fresh-schema-per-suite**. Pick the one that fits your scale.

## Per-test transactions (default)

Wrap each test in a transaction, then roll it back on teardown. The data is visible inside the test but gone afterward — no manual cleanup needed.

```python
# tests/conftest.py
import pytest
from arvel.facades import DB


@pytest.fixture(autouse=True)
async def db_transaction():
    async with DB.transaction():
        savepoint = await DB.savepoint()
        try:
            yield
        finally:
            await savepoint.rollback()
```

`autouse=True` applies the fixture to every test. The savepoint rollback unwinds everything written during the test.

This strategy is fast (no schema rebuild between tests) and isolated (no cross-test pollution). Use it as the default.

### Caveat: nested transactions

Code paths that explicitly call `DB.transaction()` inside the test will nest under the savepoint. That's fine — Arvel uses savepoints for nested transactions (ADR-043). Just don't `commit` manually in test code; let the rollback handle it.

## Fresh schema per suite

For tests that change schema (DDL — `CREATE INDEX`, `ALTER TABLE`), wrap the whole suite in a fresh-schema setup:

```python
@pytest.fixture(scope="session", autouse=True)
async def fresh_schema():
    from arvel.facades import Schema

    await Schema.drop_all()
    await Migration.run_all()
    yield
```

This rebuilds the schema once per pytest session (slower, but only paid once).

## In-memory SQLite for unit tests

For ultra-fast tests that don't need Postgres specifics, run against SQLite in memory:

```env
# .env.testing
DB_URL=sqlite+aiosqlite:///:memory:
```

A complete test suite against in-memory SQLite runs in tenths of a second. The trade-off: SQLite doesn't enforce all the constraints Postgres does (no real `ARRAY`, weaker FK checks). For features that depend on Postgres-specific behavior, use a real Postgres test database.

## Factories in tests

```python
async def test_show_user(client):
    user = await UserFactory().create()
    response = await client.get(f"/users/{user.id}")
    assert response.status_code == 200
    assert response.json()["email"] == user.email
```

See [Factories](arvent-factories.md) for the factory API.

## Seeders in tests

For tests that need a known dataset:

```python
@pytest.fixture
async def seeded_users():
    await UserFactory().count(5).create()
    yield


async def test_lists_seeded_users(client, seeded_users):
    response = await client.get("/users")
    assert response.status_code == 200
    assert len(response.json()["data"]) == 5
```

Factory and seeder calls inside per-test transactions are also rolled back, so no leakage.

## Database assertions

Beyond JSON-response checks, assert directly on the database:

```python
async def test_signup_persists_user(client):
    response = await client.post("/signup", json={"name": "Alice", "email": "a@b.com"})
    assert response.status_code == 201

    assert await User.where(email="a@b.com").exists()
    assert await User.count() == 1
```

For richer assertions:

```python
user = await User.where(email="a@b.com").first_or_fail()
assert user.name == "Alice"
assert user.created_at >= start_time
```

## Query counting

Catch N+1 regressions with `QueryLog`:

```python
from arvel.database.query_logging import QueryLog


async def test_category_list_no_n_plus_one(session):
    await CategoryFactory().count(5).create_each_with_products(3)

    with QueryLog.assert_max_queries(2):
        categories = await Category.with_("catalog_products").all()

    # exactly 2 queries: one for categories, one select-in for products
    assert len(categories) == 5
```

`QueryLog.assert_max_queries(n)` is a context manager. It records every SQL statement executed inside the block, and raises `AssertionError` (with the full query list) if more than `n` were issued. Use `n=1` for single-row fetches, `n=2` for a parent + one eager-loaded collection, etc.

To inspect queries without asserting:

```python
with QueryLog.capture() as log:
    await Category.with_("catalog_products").all()

print(len(log.queries))   # number of SQL statements
print(log.queries[0])     # first statement text
```

## Where to next?

- [HTTP Tests](http-tests.md) — combining HTTP and DB assertions.
- [Factories](arvent-factories.md) — generating test data.
- [Mocking](mocking.md) — faking the facades.
