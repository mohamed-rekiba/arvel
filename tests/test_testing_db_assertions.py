"""Testing (doc 20) — DB assertion helpers: assert_database_has/missing/count/empty/
soft_deleted/not_soft_deleted, and assert_model_exists/missing."""

from __future__ import annotations

from typing import ClassVar

import pytest
import sqlalchemy as sa

from arvel.database import Builder, ConnectionResolver, Model
from arvel.testing import (
    assert_database_count,
    assert_database_empty,
    assert_database_has,
    assert_database_missing,
    assert_model_exists,
    assert_model_missing,
    assert_not_soft_deleted,
    assert_soft_deleted,
)

users = sa.Table(
    "users",
    sa.MetaData(),
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("email", sa.String),
    sa.Column("deleted_at", sa.String),
)


async def _db() -> ConnectionResolver:
    db = ConnectionResolver()
    await db.execute(sa.schema.CreateTable(users))
    await Builder(users, db).insert({"email": "ada@example.com", "deleted_at": None})
    await Builder(users, db).insert({"email": "gone@example.com", "deleted_at": "2026-01-01"})
    return db


async def test_assert_database_has() -> None:
    db = await _db()
    try:
        await assert_database_has(db, "users", email="ada@example.com")  # passes
        with pytest.raises(AssertionError):
            await assert_database_has(db, "users", email="nobody@example.com")
    finally:
        await db.dispose()


async def test_assert_database_missing() -> None:
    db = await _db()
    try:
        await assert_database_missing(db, "users", email="nobody@example.com")  # passes
        with pytest.raises(AssertionError):
            await assert_database_missing(db, "users", email="ada@example.com")
    finally:
        await db.dispose()


async def test_assert_soft_deleted() -> None:
    db = await _db()
    try:
        await assert_soft_deleted(db, "users", email="gone@example.com")  # has deleted_at
        with pytest.raises(AssertionError):
            await assert_soft_deleted(db, "users", email="ada@example.com")  # still live
    finally:
        await db.dispose()


async def test_assert_not_soft_deleted() -> None:
    db = await _db()
    try:
        await assert_not_soft_deleted(db, "users", email="ada@example.com")  # still live
        with pytest.raises(AssertionError):
            await assert_not_soft_deleted(db, "users", email="gone@example.com")  # trashed
    finally:
        await db.dispose()


async def test_assert_database_count() -> None:
    db = await _db()
    try:
        await assert_database_count(db, "users", 2)  # whole table
        await assert_database_count(db, "users", 1, email="ada@example.com")
        with pytest.raises(AssertionError):
            await assert_database_count(db, "users", 5)
    finally:
        await db.dispose()


async def test_assert_database_empty() -> None:
    db = await _db()
    try:
        with pytest.raises(AssertionError):
            await assert_database_empty(db, "users")  # 2 rows present
        await Builder(users, db).where("email", "=", "ada@example.com").delete()
        await Builder(users, db).where("email", "=", "gone@example.com").delete()
        await assert_database_empty(db, "users")
    finally:
        await db.dispose()


class _User(Model):
    __table_name__ = "model_users"
    __fields__: ClassVar = {"email": str}
    __fillable__: ClassVar = ["email"]


async def test_assert_model_exists_and_missing() -> None:
    db = ConnectionResolver()
    _User.set_connection(db)
    await db.execute(sa.schema.CreateTable(_User.__table__))
    try:
        user = await _User.create(email="ada@example.com")
        await assert_model_exists(user)
        with pytest.raises(AssertionError):
            await assert_model_missing(user)

        await user.delete()
        await assert_model_missing(user)
        with pytest.raises(AssertionError):
            await assert_model_exists(user)
    finally:
        _User.set_connection(None)
        await db.dispose()
