"""Database test case — transaction-per-test with automatic rollback."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import text

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from arvel.data.model import ArvelModel


class DatabaseTestCase:
    """Test helper providing a database session with rollback isolation.

    Wraps an existing ``AsyncSession`` (typically from a fixture) and provides
    convenience methods for seeding data and asserting database state.

    Usage::

        @pytest.fixture
        async def db(db_session):
            return DatabaseTestCase(db_session)

        async def test_something(db):
            await db.seed([User(name="Alice")])
            await db.assert_database_has("users", {"name": "Alice"})
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @property
    def session(self) -> AsyncSession:
        return self._session

    async def seed(self, models: Sequence[ArvelModel]) -> None:
        """Add multiple model instances to the session and flush."""
        for model in models:
            self._session.add(model)
        await self._session.flush()

    async def refresh(self, instance: ArvelModel) -> None:
        """Refresh a model instance from the database."""
        await self._session.refresh(instance)

    async def assert_database_has(self, table: str, conditions: dict[str, Any]) -> None:
        """Assert at least one row matching *conditions* exists in *table*."""
        where_clauses = " AND ".join(f"{col} = :p{i}" for i, col in enumerate(conditions))
        params = {f"p{i}": v for i, v in enumerate(conditions.values())}
        stmt = text(f"SELECT 1 FROM {table} WHERE {where_clauses} LIMIT 1")  # noqa: S608
        result = await self._session.execute(stmt, params)
        if result.scalar_one_or_none() is None:
            msg = f"Expected row in '{table}' matching {conditions}, but none found"
            raise AssertionError(msg)

    async def assert_database_missing(self, table: str, conditions: dict[str, Any]) -> None:
        """Assert no row matching *conditions* exists in *table*."""
        where_clauses = " AND ".join(f"{col} = :p{i}" for i, col in enumerate(conditions))
        params = {f"p{i}": v for i, v in enumerate(conditions.values())}
        stmt = text(f"SELECT 1 FROM {table} WHERE {where_clauses} LIMIT 1")  # noqa: S608
        result = await self._session.execute(stmt, params)
        if result.scalar_one_or_none() is not None:
            msg = f"Expected no row in '{table}' matching {conditions}, but found one"
            raise AssertionError(msg)

    async def assert_database_count(self, table: str, expected: int) -> None:
        """Assert the total number of rows in *table* equals *expected*."""
        stmt = text(f"SELECT COUNT(*) FROM {table}")  # noqa: S608
        result = await self._session.execute(stmt)
        actual = result.scalar_one()
        if actual != expected:
            msg = f"Expected {expected} rows in '{table}', but found {actual}"
            raise AssertionError(msg)

    def assert_soft_deleted(self, instance: Any) -> None:
        """Assert *instance* has a non-null ``deleted_at`` timestamp."""
        deleted_at = getattr(instance, "deleted_at", None)
        if deleted_at is None:
            type_name = type(instance).__name__
            msg = f"Expected {type_name} to be soft-deleted, but deleted_at is None"
            raise AssertionError(msg)
