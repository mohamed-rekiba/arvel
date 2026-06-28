"""Testing (doc 20) — transactional rollback isolates DB writes per test."""

from __future__ import annotations

from typing import ClassVar

import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model
from arvel.testing import database_transaction


class Widget(Model):
    __fields__: ClassVar = {"name": str}
    __fillable__: ClassVar = ["name"]


async def test_rollback_isolates_writes() -> None:
    db = ConnectionResolver()
    Widget.set_connection(db)
    await db.execute(sa.schema.CreateTable(Widget.__table__))  # committed (table persists)
    try:
        async with database_transaction(db):
            await Widget.create(name="temp")
            assert len(await Widget.get()) == 1  # visible inside the transaction
        assert len(await Widget.get()) == 0  # rolled back afterward
    finally:
        await db.dispose()
