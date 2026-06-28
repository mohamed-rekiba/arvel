"""Integration (doc 20) — database_transaction rolls back on a real Postgres (isolation fixture)."""

from __future__ import annotations

from typing import ClassVar

import pytest
import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model
from arvel.testing import database_transaction

pytestmark = pytest.mark.integration


class Account(Model):
    __fields__: ClassVar = {"owner": str, "balance": int}
    __fillable__: ClassVar = ["owner", "balance"]


async def test_rollback_isolates_writes_on_postgres(postgres_url: str) -> None:
    db = ConnectionResolver({"default": {"url": postgres_url}})
    Account.set_connection(db)
    try:
        await db.execute(sa.schema.CreateTable(Account.__table__))  # committed: table persists

        async with database_transaction(db):
            await Account.create(owner="ada", balance=100)
            assert await Account.count() == 1  # visible inside the transaction
        assert await Account.count() == 0  # rolled back on a real DB

        # a committed row, by contrast, survives
        await Account.create(owner="grace", balance=50)
        assert await Account.count() == 1
    finally:
        await db.execute(sa.schema.DropTable(Account.__table__))
        await db.dispose()
