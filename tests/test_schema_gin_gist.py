"""GIN / GiST access-method indexes on the Blueprint — for jsonb/array/tsvector (GIN) and
geometric/range/tsvector (GiST). Renders `USING gin`/`USING gist` on Postgres, a plain index on
other dialects, and is emitted as a `create_index` op by the migrator."""

from __future__ import annotations

from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from arvel.database import ConnectionResolver
from arvel.database.migrations import Schema
from arvel.database.schema import Blueprint


def _blueprint() -> Blueprint:
    bp = Blueprint("docs")
    bp.id()
    bp.jsonb("data")
    bp.gin_index("data")
    return bp


def test_gin_index_renders_using_gin_on_postgres() -> None:
    table = _blueprint().to_table()
    index = next(i for i in table.indexes if i.name == "docs_data_gin")
    ddl = str(sa.schema.CreateIndex(index).compile(dialect=postgresql.dialect()))
    assert "USING gin" in ddl
    assert "data" in ddl


def test_gist_index_renders_using_gist_on_postgres() -> None:
    bp = Blueprint("shapes")
    bp.id()
    bp.string("region")
    bp.gist_index("region", name="shapes_region_gist")
    index = next(iter(bp.to_table().indexes))
    ddl = str(sa.schema.CreateIndex(index).compile(dialect=postgresql.dialect()))
    assert "USING gist" in ddl


async def test_index_is_cross_dialect_safe_on_sqlite() -> None:
    table = _blueprint().to_table()
    db = ConnectionResolver()
    try:
        await db.execute(sa.schema.CreateTable(table))
        for index in table.indexes:  # postgresql_using is ignored on sqlite → plain index
            await db.execute(sa.schema.CreateIndex(index))
    finally:
        await db.dispose()


def test_migrator_emits_create_index_for_gin() -> None:
    class _Op:
        def __init__(self) -> None:
            self.calls: list[tuple[Any, ...]] = []

        def create_table(self, name: str, *cols: Any) -> None:
            self.calls.append(("create_table", name))

        def create_index(self, *args: Any, **kwargs: Any) -> None:
            self.calls.append(("create_index", args, kwargs))

    op = _Op()
    Schema(op).create("docs", lambda t: (t.id(), t.jsonb("data"), t.gin_index("data")))
    created = [c for c in op.calls if c[0] == "create_index"]
    assert len(created) == 1
    _, args, kwargs = created[0]
    assert args == ("docs_data_gin", "docs", ["data"])
    assert kwargs == {"postgresql_using": "gin"}


def test_index_requires_a_column() -> None:
    with pytest.raises(ValueError, match="requires at least one column"):
        Blueprint("docs").gin_index()
