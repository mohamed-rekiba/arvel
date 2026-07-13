"""09 DB-QUERY A4 — upsert() is dialect-correct: Postgres/SQLite use ON CONFLICT DO UPDATE,
MySQL/MariaDB use ON DUPLICATE KEY UPDATE, and an unrecognized dialect raises rather than
silently emitting the wrong SQL. The dialect-selection statements are asserted here without a
real network connection (`execute()` is patched to capture the statement); the actual
round-trip against real Postgres/MySQL/SQLite is covered in tests/integration/."""

from __future__ import annotations

from typing import Any

import pytest
import sqlalchemy as sa
import sqlalchemy.dialects.mysql
import sqlalchemy.dialects.postgresql

from arvel.database import ConnectionResolver, UnsupportedDriverOperation
from arvel.database.builder import Builder
from arvel.database.connections import WriteResult

_md = sa.MetaData()
products = sa.Table(
    "products",
    _md,
    sa.Column("sku", sa.String, primary_key=True),
    sa.Column("price", sa.Integer),
)


async def _capture_upsert_statement(url: str) -> Any:
    """Build the upsert() statement for a connection at `url` WITHOUT hitting the network —
    `execute()` is patched to capture the statement instead of running it (the dialect is known
    from the URL the instant the (unconnected) async engine is created)."""
    db = ConnectionResolver({"default": {"url": url}})
    captured: dict[str, Any] = {}

    async def fake_execute(statement: Any, name: str | None = None) -> WriteResult:
        captured["statement"] = statement
        return WriteResult(rowcount=1)

    db.execute = fake_execute  # type: ignore[method-assign]
    await Builder(products, db).upsert([{"sku": "A", "price": 10}], ["sku"], ["price"])
    return captured["statement"]


async def test_upsert_uses_on_duplicate_key_update_on_mysql() -> None:
    stmt = await _capture_upsert_statement("mysql+asyncmy://u:p@127.0.0.1/db")
    compiled = str(stmt.compile(dialect=sa.dialects.mysql.dialect())).upper()
    assert "ON DUPLICATE KEY UPDATE" in compiled


async def test_upsert_uses_on_duplicate_key_update_on_mariadb() -> None:
    stmt = await _capture_upsert_statement("mariadb+asyncmy://u:p@127.0.0.1/db")
    compiled = str(stmt.compile(dialect=sa.dialects.mysql.dialect())).upper()
    assert "ON DUPLICATE KEY UPDATE" in compiled


async def test_upsert_uses_on_conflict_on_postgresql() -> None:
    stmt = await _capture_upsert_statement("postgresql+asyncpg://u:p@127.0.0.1/db")
    compiled = str(stmt.compile(dialect=sa.dialects.postgresql.dialect())).upper()
    assert "ON CONFLICT" in compiled


async def test_upsert_uses_on_conflict_on_sqlite() -> None:
    stmt = await _capture_upsert_statement("sqlite+aiosqlite://")
    compiled = str(stmt.compile(dialect=sa.dialects.sqlite.dialect())).upper()
    assert "ON CONFLICT" in compiled


async def test_upsert_raises_on_unsupported_dialect() -> None:
    """An unrecognized dialect must raise, never fall back to a (wrong) default (A4)."""

    class _FakeDialect:
        name = "oracle"

    class _FakeEngine:
        dialect = _FakeDialect()

    db = ConnectionResolver()
    db.engine = lambda *args, **kwargs: _FakeEngine()  # type: ignore[method-assign]
    with pytest.raises(UnsupportedDriverOperation):
        await Builder(products, db).upsert([{"sku": "A", "price": 10}], ["sku"])
