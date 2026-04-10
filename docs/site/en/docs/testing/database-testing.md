# Database Testing

Database tests are the ones that catch the mistakes unit tests miss: a constraint you forgot, a soft-delete flag that never flips, a repository method that returns the wrong row. Arvel encourages you to run those tests against a **real async engine**—typically **SQLite with aiosqlite** in CI and local dev—and to wrap each test in a **transaction that rolls back** so files stay clean and tests stay parallel-friendly.

This page covers that isolation model, **`DatabaseTestCase`**, **`ModelFactory`** / **`FactoryBuilder`**, and how to seed and assert without turning tests into copy-pasted SQL.

## Why transaction rollback

The pattern that works well: open a connection, **`begin()`** a transaction, yield an **`AsyncSession`** with **`expire_on_commit=False`**, then **`rollback()`** in teardown (whether the test passed or failed). Nothing persists after the test, so order does not matter and you are not deleting rows by hand.

A simplified fixture often looks like this:

```python
import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_fk(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.connect() as conn:
        trans = await conn.begin()
        async with AsyncSession(bind=conn, expire_on_commit=False) as session:
            yield session
        if trans.is_active:
            await trans.rollback()

    await engine.dispose()
```

**`expire_on_commit=False`** matters: after a flush or commit in the test, you can still read relationship attributes without lazy-load surprises in async code.

Session-scoped migrations (create tables once) and file-backed SQLite with locks are common when tests grow—mirror what Arvel’s own data tests do if you need multi-worker safety.

## DatabaseTestCase

**`DatabaseTestCase`** wraps an **`AsyncSession`** and gives you ergonomic helpers: seed model instances, refresh from the database, and assert row presence or counts with plain dictionaries—no raw SQL in every test unless you want it.

```python
import pytest
from arvel.testing import DatabaseTestCase

from myapp.models import User


@pytest.fixture
async def db(db_session):
    return DatabaseTestCase(db_session)


@pytest.mark.db
@pytest.mark.anyio
async def test_seed_and_assert(db: DatabaseTestCase):
    await db.seed([User(name="Alice", email="alice@example.com")])

    await db.assert_database_has("users", {"email": "alice@example.com"})
    await db.assert_database_count("users", 1)
```

**`assert_database_missing`** checks that no row matches the given columns, and **`assert_soft_deleted`** asserts a model instance has a non-null **`deleted_at`** when you use soft deletes.

Use these helpers for “did persistence do what we think?” assertions after an HTTP test or service call that runs on the same session.

## ModelFactory and FactoryBuilder

Factories keep tests readable. Subclass **`ModelFactory`** for each model, override **`defaults()`**, and use **`_next_seq()`** when you need unique emails or slugs. **`make()`** builds an in-memory instance; **`create()`** persists through a session; **`create_many()`** and **`make_batch()`** scale up lists.

```python
from typing import Any, ClassVar

from arvel.testing import ModelFactory

from myapp.models import User


class UserFactory(ModelFactory[User]):
    __model__ = User

    @classmethod
    def defaults(cls) -> dict[str, Any]:
        seq = cls._next_seq()
        return {
            "name": f"User {seq}",
            "email": f"user{seq}@test.invalid",
        }

    @classmethod
    def state_admin(cls) -> dict[str, Any]:
        return {"name": "Admin", "is_admin": True}
```

**`UserFactory.state("admin")`** returns a **`FactoryBuilder`** so you can chain **`make()`**, **`create()`**, or **`create_many()`** with that state applied—similar to Laravel factory states, without magic strings scattered across the suite.

```python
admin = UserFactory.state("admin").make()
users = await UserFactory.create_many(5, session=session)
```

## Seeding in tests

You have three good options, often combined:

1. **Factories** — default and named states for happy paths.
2. **`DatabaseTestCase.seed()`** — pass a list of already-built models when the arrangement is one-off.
3. **Transaction-scoped fixtures** — create a baseline user or tenant once per test via a fixture that depends on **`db_session`**.

Avoid committing data that outlives the test unless you are deliberately integration-testing against a shared database (rare in application tests).

## Assertions that match how you think

After an action, assert at the layer that proves the bug you are afraid of:

- **HTTP + DB** — hit the route, then **`assert_database_has`** for the row you expect.
- **Repository** — call the repository directly inside the same session fixture and compare model fields or use **`db.refresh(instance)`** before asserting.

Keep tests deterministic: no reliance on wall-clock time without freezing, no ordering assumptions between tests, and no shared mutable module state. If a test needs “exactly one row in `posts`”, **`assert_database_count`** says so explicitly.

Database testing in Arvel is meant to feel grounded—real SQLAlchemy async sessions, real constraints, rollback isolation—so when you merge, you trust both the HTTP layer and the data layer together.
