"""DB.table() — a schema-less query builder over a raw table/view, plus
the ``dialect()`` accessor. Unlike a model query it does not hydrate (rows are plain ``dict``); its
columns resolve as strictly-validated identifiers, so joined ``table.column`` filters work while an
injection payload is still rejected."""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from arvel.database.connections import ConnectionResolver


@pytest.fixture
async def db():
    resolver = ConnectionResolver({"default": {"url": "sqlite+aiosqlite://"}})
    async with resolver.engine().begin() as conn:
        await conn.execute(sa.text("CREATE TABLE items(id INTEGER PRIMARY KEY, cat TEXT, qty INT)"))
        await conn.execute(
            sa.text("INSERT INTO items(cat, qty) VALUES ('a', 2), ('a', 3), ('b', 5)")
        )
    yield resolver
    await resolver.dispose()


async def test_select_star_returns_plain_dicts(db: ConnectionResolver) -> None:
    rows = await db.table("items").where("cat", "a").order_by("id").get()
    assert rows == [{"id": 1, "cat": "a", "qty": 2}, {"id": 2, "cat": "a", "qty": 3}]
    assert isinstance(rows[0], dict)  # non-hydrating — no model


async def test_grouped_aggregate_via_pluck(db: ConnectionResolver) -> None:
    sold = (
        await db.table("items").group_by("cat").select_raw("cat, SUM(qty) AS s").pluck("s", "cat")
    )
    assert sold == {"a": 5, "b": 5}


async def test_qualified_join_column_filter(db: ConnectionResolver) -> None:
    # a schema-less builder owns its identifiers → a joined `table.column` filter is allowed
    rows = await db.table("items").where_in("items.cat", ["b"]).get()
    assert [r["id"] for r in rows] == [3]


async def test_dialect_accessor(db: ConnectionResolver) -> None:
    assert db.dialect() == "sqlite"


async def test_refresh_materialized_view_noop_off_postgres(db: ConnectionResolver) -> None:
    # sqlite has no materialized views (create_materialized_view degrades to a plain view) → no-op
    await db.refresh_materialized_view("items", concurrently=True)


@pytest.mark.parametrize(
    "payload",
    ["id; DROP TABLE items--", "cat' OR '1'='1", "1=1", "id, (SELECT 1)", "*", 'a"'],
)
async def test_injection_identifier_is_rejected(db: ConnectionResolver, payload: str) -> None:
    # even on the schema-less builder, a non-identifier column never becomes a literal
    with pytest.raises(KeyError):
        await db.table("items").where(payload, "x").get()
