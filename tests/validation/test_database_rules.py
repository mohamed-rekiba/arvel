"""Tests for database-aware validation rules — Story 2.

Tests must compile but FAIL until implementation exists.
Uses real SQLite DB via the db_session fixture.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column  # noqa: TC002 — Mapped needed at runtime by SA ORM

from arvel.data.model import ArvelModel

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class ValidationUser(ArvelModel):
    __tablename__ = "validation_users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254), unique=True)


class ValidationRole(ArvelModel):
    __tablename__ = "validation_roles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))


# ──── Unique Rule ────


@pytest.mark.db
async def test_unique_passes_when_no_duplicate(db_session: AsyncSession):
    from arvel.validation.rules.database import Unique

    rule = Unique("validation_users", "email", session=db_session)
    result = await rule.passes("email", "fresh@example.com", {})
    assert result is True


@pytest.mark.db
async def test_unique_fails_when_duplicate_exists(db_session: AsyncSession):
    user = ValidationUser(name="Alice", email="alice@example.com")
    db_session.add(user)
    await db_session.flush()

    from arvel.validation.rules.database import Unique

    rule = Unique("validation_users", "email", session=db_session)
    result = await rule.passes("email", "alice@example.com", {})
    assert result is False


@pytest.mark.db
async def test_unique_ignore_self(db_session: AsyncSession):
    user = ValidationUser(name="Alice", email="alice@example.com")
    db_session.add(user)
    await db_session.flush()

    from arvel.validation.rules.database import Unique

    rule = Unique("validation_users", "email", session=db_session, ignore=user.id)
    result = await rule.passes("email", "alice@example.com", {})
    assert result is True


@pytest.mark.db
async def test_unique_without_session_raises_value_error():
    from arvel.validation.rules.database import Unique

    rule = Unique("validation_users", "email", session=None)
    with pytest.raises(ValueError, match="requires a database session"):
        await rule.passes("email", "test@example.com", {})


@pytest.mark.db
async def test_unique_message():
    from arvel.validation.rules.database import Unique

    rule = Unique("validation_users", "email", session=None)
    assert "already been taken" in rule.message().lower()


# ──── Exists Rule ────


@pytest.mark.db
async def test_exists_passes_when_record_found(db_session: AsyncSession):
    role = ValidationRole(name="admin")
    db_session.add(role)
    await db_session.flush()

    from arvel.validation.rules.database import Exists

    rule = Exists("validation_roles", "id", session=db_session)
    result = await rule.passes("role_id", role.id, {})
    assert result is True


@pytest.mark.db
async def test_exists_fails_when_record_not_found(db_session: AsyncSession):
    from arvel.validation.rules.database import Exists

    rule = Exists("validation_roles", "id", session=db_session)
    result = await rule.passes("role_id", 99999, {})
    assert result is False


@pytest.mark.db
async def test_exists_without_session_raises_value_error():
    from arvel.validation.rules.database import Exists

    rule = Exists("validation_roles", "id", session=None)
    with pytest.raises(ValueError, match="requires a database session"):
        await rule.passes("role_id", 1, {})


@pytest.mark.db
async def test_exists_message():
    from arvel.validation.rules.database import Exists

    rule = Exists("validation_roles", "id", session=None)
    assert "invalid" in rule.message().lower()


# ──── Edge Cases ────


@pytest.mark.db
async def test_unique_with_empty_string(db_session: AsyncSession):
    from arvel.validation.rules.database import Unique

    rule = Unique("validation_users", "email", session=db_session)
    result = await rule.passes("email", "", {})
    assert result is True


@pytest.mark.db
async def test_exists_with_none_value(db_session: AsyncSession):
    from arvel.validation.rules.database import Exists

    rule = Exists("validation_roles", "id", session=db_session)
    result = await rule.passes("role_id", None, {})
    assert result is False
