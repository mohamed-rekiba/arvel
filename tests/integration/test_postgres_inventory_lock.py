"""The unit suite only checks that ``FOR UPDATE`` compiles; this proves two concurrent transactions
decrementing the same one-in-stock row actually serialize on the lock, so exactly one succeeds.
"""

from __future__ import annotations

import asyncio
from typing import ClassVar

import pytest
import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model

pytestmark = pytest.mark.integration


class Stock(Model):
    __table_name__ = "stock"
    __fields__: ClassVar = {"units": int}
    __fillable__: ClassVar = ["units"]


async def test_lock_for_update_serializes_concurrent_decrements(postgres_url: str) -> None:
    db = ConnectionResolver({"default": {"url": postgres_url}})
    Stock.set_connection(db)
    await db.execute(sa.schema.CreateTable(Stock.__table__))
    try:
        row = await Stock.create(units=1)

        async def buy() -> bool:
            # own asyncio Task → own connection → a real second transaction that must block on the lock
            async with db.transaction():
                locked = await Stock.where("id", row.id).lock_for_update().first()
                if locked.units < 1:
                    return False
                await asyncio.sleep(0.1)  # widen the window the lock must protect
                locked.units = locked.units - 1
                await locked.save()
                return True

        results = await asyncio.gather(buy(), buy())

        assert sum(1 for ok in results if ok) == 1
        final = await Stock.find(row.id)
        assert final.units == 0
    finally:
        await db.execute(sa.schema.DropTable(Stock.__table__))
        await db.dispose()
