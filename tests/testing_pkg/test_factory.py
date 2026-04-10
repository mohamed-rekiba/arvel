"""Tests for ModelFactory — FR-009 to FR-013, SEC-003."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from dirty_equals import IsPositiveInt

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from arvel.testing.factory import ModelFactory

from .conftest import SampleUser


class SampleUserFactory(ModelFactory[SampleUser]):
    __model__ = SampleUser

    @classmethod
    def defaults(cls) -> dict:
        seq = cls._next_seq()
        return {
            "name": f"Test User {seq}",
            "email": f"user{seq}@test.com",
        }


class TestModelFactory:
    def test_make_returns_instance(self) -> None:
        """FR-011: make() returns an in-memory instance."""
        user = SampleUserFactory.make()
        assert isinstance(user, SampleUser)
        assert user.name.startswith("Test User")
        assert "@test.com" in user.email

    def test_make_with_overrides(self) -> None:
        """FR-013: overrides are applied."""
        user = SampleUserFactory.make(email="custom@test.com")
        assert user.email == "custom@test.com"
        assert user.name.startswith("Test User")

    @pytest.mark.anyio
    async def test_create_persists(self, db_session: AsyncSession) -> None:
        """FR-010: create() persists to database."""
        user = await SampleUserFactory.create(session=db_session, email="persisted@test.com")
        assert user.id == IsPositiveInt
        assert user.email == "persisted@test.com"

    @pytest.mark.anyio
    async def test_batch_creates_multiple(self, db_session: AsyncSession) -> None:
        """FR-012: batch(n) creates n instances."""
        users = await SampleUserFactory.batch(3, session=db_session)
        assert len(users) == 3
        for u in users:
            assert u.id == IsPositiveInt

    def test_make_batch_in_memory(self) -> None:
        """FR-012: make_batch returns n in-memory instances."""
        users = SampleUserFactory.make_batch(5)
        assert len(users) == 5
        for u in users:
            assert isinstance(u, SampleUser)
