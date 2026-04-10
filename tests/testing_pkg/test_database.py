"""Tests for DatabaseTestCase — FR-005 to FR-008."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from arvel.testing.database import DatabaseTestCase

from .conftest import SampleUser


class TestDatabaseTestCase:
    @pytest.mark.anyio
    async def test_provides_session(self, db_session: AsyncSession) -> None:
        """FR-007: db_session fixture provides async session."""
        tc = DatabaseTestCase(db_session)
        assert tc.session is not None
        assert isinstance(tc.session, AsyncSession)

    @pytest.mark.anyio
    async def test_add_and_query_within_transaction(self, db_session: AsyncSession) -> None:
        """FR-005: data within a test is visible."""
        tc = DatabaseTestCase(db_session)
        user = SampleUser(name="Alice", email="alice@test.com")
        tc.session.add(user)
        await tc.session.flush()

        from sqlalchemy import select

        result = await tc.session.execute(select(SampleUser).where(SampleUser.name == "Alice"))
        found = result.scalar_one_or_none()
        assert found is not None
        assert found.email == "alice@test.com"

    @pytest.mark.anyio
    async def test_rollback_isolates_tests(self, db_session: AsyncSession) -> None:
        """FR-006: each test sees clean state (previous test's data rolled back)."""
        from sqlalchemy import select

        result = await db_session.execute(select(SampleUser).where(SampleUser.name == "Alice"))
        found = result.scalar_one_or_none()
        assert found is None

    @pytest.mark.anyio
    async def test_seed_helper(self, db_session: AsyncSession) -> None:
        """FR-005: seed helper adds multiple records."""
        tc = DatabaseTestCase(db_session)
        users = [
            SampleUser(name="Bob", email="bob@test.com"),
            SampleUser(name="Carol", email="carol@test.com"),
        ]
        await tc.seed(users)

        from sqlalchemy import func, select

        result = await db_session.execute(select(func.count()).select_from(SampleUser))
        count = result.scalar()
        assert count is not None
        assert count >= 2
