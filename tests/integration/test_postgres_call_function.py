"""Integration (doc 08/20) — db.call_function invokes a real plpgsql function on Postgres (D7)."""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from arvel.database import ConnectionResolver
from arvel.database.schema import create_function

pytestmark = pytest.mark.integration


async def test_call_function_runs_real_db_function(postgres_url: str) -> None:
    db = ConnectionResolver({"default": {"url": postgres_url}})
    try:
        await db.execute(
            create_function(
                "add_two",
                [("a", "integer"), ("b", "integer")],
                returns="integer",
                body="BEGIN RETURN a + b; END;",
            )
        )
        result = await db.call_function("add_two", 40, 2)
        assert result == 42
    finally:
        await db.execute(sa.text("DROP FUNCTION IF EXISTS add_two(integer, integer)"))
        await db.dispose()
