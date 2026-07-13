"""DB (doc 08) — @db.transactional decorator: commit on return, rollback on raise."""

from __future__ import annotations

from typing import ClassVar

import pytest
import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model


class Account(Model):
    __fields__: ClassVar = {"owner": str}
    __fillable__: ClassVar = ["owner"]


async def _setup() -> ConnectionResolver:
    db = ConnectionResolver()
    Account.set_connection(db)
    await db.execute(sa.schema.CreateTable(Account.__table__))
    return db


async def test_transactional_commits_on_return() -> None:
    db = await _setup()
    try:

        @db.transactional
        async def make_two() -> int:
            await Account.create(owner="ada")
            await Account.create(owner="grace")
            return 2

        assert await make_two() == 2
        assert await Account.count() == 2  # committed
    finally:
        await db.dispose()


async def test_transactional_rolls_back_on_raise() -> None:
    db = await _setup()
    try:

        @db.transactional
        async def boom() -> None:
            await Account.create(owner="ada")
            raise RuntimeError("fail after a write")

        with pytest.raises(RuntimeError):
            await boom()
        assert await Account.count() == 0  # rolled back — the write didn't persist
    finally:
        await db.dispose()
