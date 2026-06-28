"""Testing (doc 20) — DB assertion helpers: assert_database_has/missing/soft_deleted."""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from arvel.database import Builder, ConnectionResolver
from arvel.testing import assert_database_has, assert_database_missing, assert_soft_deleted

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
