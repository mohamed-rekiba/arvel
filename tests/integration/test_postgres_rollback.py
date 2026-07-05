"""database_transaction rolls back on a real Postgres (isolation fixture)."""

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
        # self-heal against a table leaked by a prior interrupted run on the reused container
        await db.execute(sa.schema.DropTable(Account.__table__, if_exists=True))
        await db.execute(sa.schema.CreateTable(Account.__table__))

        async with database_transaction(db):
            await Account.create(owner="ada", balance=100)
            assert await Account.count() == 1
        assert await Account.count() == 0  # rolled back on a real DB

        await Account.create(owner="grace", balance=50)
        assert await Account.count() == 1
    finally:
        await db.execute(sa.schema.DropTable(Account.__table__))
        await db.dispose()
