"""Validation (doc 10) — async DB rules: unique / exists. Test-first."""

from __future__ import annotations

import sqlalchemy as sa

from arvel.database import Builder, ConnectionResolver
from arvel.validation import Validator

users = sa.Table(
    "users",
    sa.MetaData(),
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("email", sa.String),
)


async def _db() -> ConnectionResolver:
    db = ConnectionResolver()
    await db.execute(sa.schema.CreateTable(users))
    await Builder(users, db).insert({"email": "taken@example.com"})
    return db


async def test_unique_passes_for_new_value() -> None:
    db = await _db()
    try:
        validator = Validator(
            {"email": "free@example.com"}, {"email": "unique:users,email"}, connection=db
        )
        assert await validator.passes_async()
    finally:
        await db.dispose()


async def test_unique_fails_for_taken_value() -> None:
    db = await _db()
    try:
        validator = Validator(
            {"email": "taken@example.com"}, {"email": "unique:users,email"}, connection=db
        )
        assert await validator.fails_async()
        assert "email" in validator.errors()
    finally:
        await db.dispose()


async def test_exists_passes_when_present_fails_when_absent() -> None:
    db = await _db()
    try:
        present = Validator(
            {"email": "taken@example.com"}, {"email": "exists:users,email"}, connection=db
        )
        assert await present.passes_async()

        absent = Validator(
            {"email": "ghost@example.com"}, {"email": "exists:users,email"}, connection=db
        )
        assert await absent.fails_async()
    finally:
        await db.dispose()


async def test_async_path_still_runs_sync_rules() -> None:
    db = await _db()
    try:
        # 'required' (sync) + 'unique' (async) together: empty value fails on required
        validator = Validator(
            {"email": ""}, {"email": "required|unique:users,email"}, connection=db
        )
        assert await validator.fails_async()
        assert "email" in validator.errors()
    finally:
        await db.dispose()
