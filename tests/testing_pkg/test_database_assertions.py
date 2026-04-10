"""Tests for DatabaseTestCase assertion methods — Story 2, all 5 ACs."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from arvel.testing.database import DatabaseTestCase

from .conftest import SampleUser

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
async def db(db_session: AsyncSession) -> DatabaseTestCase:
    return DatabaseTestCase(db_session)


class TestAssertDatabaseHas:
    """AC-S2-1: assert_database_has passes when matching row exists."""

    @pytest.mark.anyio
    async def test_has_matching_row(self, db: DatabaseTestCase, db_session: AsyncSession) -> None:
        user = SampleUser(name="Alice", email="alice@test.com")
        db_session.add(user)
        await db_session.flush()

        await db.assert_database_has("test_users", {"email": "alice@test.com"})

    @pytest.mark.anyio
    async def test_has_no_matching_row(self, db: DatabaseTestCase) -> None:
        with pytest.raises(AssertionError, match="Expected row in 'test_users'"):
            await db.assert_database_has("test_users", {"email": "nonexistent@test.com"})

    @pytest.mark.anyio
    async def test_has_multiple_conditions(
        self, db: DatabaseTestCase, db_session: AsyncSession
    ) -> None:
        user = SampleUser(name="Bob", email="bob@test.com")
        db_session.add(user)
        await db_session.flush()

        await db.assert_database_has("test_users", {"name": "Bob", "email": "bob@test.com"})


class TestAssertDatabaseMissing:
    """AC-S2-2: assert_database_missing passes when no matching row exists."""

    @pytest.mark.anyio
    async def test_missing_passes(self, db: DatabaseTestCase) -> None:
        await db.assert_database_missing("test_users", {"email": "deleted@test.com"})

    @pytest.mark.anyio
    async def test_missing_fails_when_exists(
        self, db: DatabaseTestCase, db_session: AsyncSession
    ) -> None:
        user = SampleUser(name="Charlie", email="charlie@test.com")
        db_session.add(user)
        await db_session.flush()

        with pytest.raises(AssertionError, match="Expected no row in 'test_users'"):
            await db.assert_database_missing("test_users", {"email": "charlie@test.com"})


class TestAssertDatabaseCount:
    """AC-S2-3: assert_database_count passes when row count matches."""

    @pytest.mark.anyio
    async def test_count_matches(self, db: DatabaseTestCase, db_session: AsyncSession) -> None:
        for i in range(3):
            db_session.add(SampleUser(name=f"User {i}", email=f"user{i}@test.com"))
        await db_session.flush()

        await db.assert_database_count("test_users", 3)

    @pytest.mark.anyio
    async def test_count_mismatch(self, db: DatabaseTestCase) -> None:
        with pytest.raises(AssertionError, match="Expected 5 rows in 'test_users'"):
            await db.assert_database_count("test_users", 5)

    @pytest.mark.anyio
    async def test_count_empty_table(self, db: DatabaseTestCase) -> None:
        await db.assert_database_count("test_users", 0)


class TestAssertSoftDeleted:
    """AC-S2-4: assert_soft_deleted checks deleted_at is not null."""

    @pytest.mark.anyio
    async def test_soft_deleted_passes(self, db: DatabaseTestCase) -> None:
        from datetime import UTC, datetime
        from unittest.mock import MagicMock

        instance = MagicMock()
        instance.deleted_at = datetime.now(UTC)
        db.assert_soft_deleted(instance)

    @pytest.mark.anyio
    async def test_soft_deleted_fails(self, db: DatabaseTestCase) -> None:
        from unittest.mock import MagicMock

        instance = MagicMock()
        instance.deleted_at = None
        with pytest.raises(AssertionError, match=r"Expected .* to be soft-deleted"):
            db.assert_soft_deleted(instance)


class TestAssertionErrorMessages:
    """AC-S2-5: Error messages include table name, conditions, and actual state."""

    @pytest.mark.anyio
    async def test_has_error_includes_table(self, db: DatabaseTestCase) -> None:
        try:
            await db.assert_database_has("test_users", {"email": "missing@test.com"})
        except AssertionError as e:
            msg = str(e)
            assert "test_users" in msg
            assert "email" in msg

    @pytest.mark.anyio
    async def test_count_error_includes_actual(
        self, db: DatabaseTestCase, db_session: AsyncSession
    ) -> None:
        db_session.add(SampleUser(name="One", email="one@test.com"))
        await db_session.flush()

        try:
            await db.assert_database_count("test_users", 99)
        except AssertionError as e:
            msg = str(e)
            assert "99" in msg
            assert "1" in msg
