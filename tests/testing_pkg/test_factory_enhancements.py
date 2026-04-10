"""Tests for ModelFactory enhancements — Story 4, all 6 ACs."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from dirty_equals import IsPositiveInt

from arvel.testing.factory import ModelFactory

from .conftest import SampleUser

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class EnhancedUserFactory(ModelFactory[SampleUser]):
    __model__ = SampleUser

    @classmethod
    def defaults(cls) -> dict[str, Any]:
        seq = cls._next_seq()
        return {"name": f"User {seq}", "email": f"user{seq}@factory.com"}

    @classmethod
    def state_admin(cls) -> dict[str, Any]:
        return {"name": "Admin User"}

    @classmethod
    def state_test(cls) -> dict[str, Any]:
        return {"name": "Test User", "email": "test@factory.com"}


class TestFactoryState:
    """AC-S4-3: state() applies named defaults."""

    def test_state_applies_overrides(self) -> None:
        user = EnhancedUserFactory.state("admin").make()
        assert user.name == "Admin User"
        assert "@factory.com" in user.email

    def test_state_with_explicit_override(self) -> None:
        user = EnhancedUserFactory.state("test").make(email="custom@test.com")
        assert user.name == "Test User"
        assert user.email == "custom@test.com"

    def test_state_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown state 'nonexistent'"):
            EnhancedUserFactory.state("nonexistent")


class TestCreateMany:
    """AC-S4-4: create_many creates multiple with unique data."""

    @pytest.mark.anyio
    async def test_create_many(self, db_session: AsyncSession) -> None:
        users = await EnhancedUserFactory.create_many(5, session=db_session)
        assert len(users) == 5
        emails = {u.email for u in users}
        assert len(emails) == 5
        for u in users:
            assert u.id == IsPositiveInt

    def test_make_many_in_memory(self) -> None:
        users = EnhancedUserFactory.make_batch(3)
        assert len(users) == 3
        names = {u.name for u in users}
        assert len(names) == 3


class TestFactoryStateWithCreate:
    """AC-S4-3 + AC-S4-2: state() works with create()."""

    @pytest.mark.anyio
    async def test_state_create(self, db_session: AsyncSession) -> None:
        user = await EnhancedUserFactory.state("admin").create(session=db_session)
        assert user.id == IsPositiveInt
        assert user.name == "Admin User"

    @pytest.mark.anyio
    async def test_state_batch(self, db_session: AsyncSession) -> None:
        users = await EnhancedUserFactory.state("admin").create_many(3, session=db_session)
        assert len(users) == 3
        for u in users:
            assert u.name == "Admin User"
            assert u.id == IsPositiveInt
