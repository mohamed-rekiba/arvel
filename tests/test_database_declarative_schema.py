"""Advanced DB (doc 08) — declarative View/MaterializedView/DatabaseFunction (D4).

These are thin declarative wrappers over the existing schema ops (DR-0006): the class
declares name/query/etc.; ``.create()`` resolves to the same op function call. ``query``
may be a Builder (``.to_select()``) or a raw Core selectable.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa

from arvel.database.schema import DatabaseFunction, MaterializedView, View


class _StubBuilder:
    """Stands in for a real arvel Builder — exposes to_select() like the Builder does."""

    def __init__(self, selectable: Any) -> None:
        self._s = selectable

    def to_select(self) -> Any:
        return self._s


_users = sa.table("users", sa.column("id"), sa.column("active"))


def test_view_create_wraps_create_view() -> None:
    class ActiveUsers(View):
        name = "active_users"
        query = _StubBuilder(sa.select(_users.c.id).where(_users.c.active.is_(True)))

    ddl = str(ActiveUsers().create())
    assert "CREATE VIEW active_users AS" in ddl
    assert "SELECT" in ddl.upper()


def test_view_accepts_raw_selectable() -> None:
    class AllUsers(View):
        name = "all_users"
        query = sa.select(_users.c.id)

    assert "CREATE VIEW all_users AS" in str(AllUsers().create())


def test_materialized_view_create_and_refresh() -> None:
    class MonthlyRevenue(MaterializedView):
        name = "monthly_revenue"
        query = sa.select(_users.c.id)
        refresh = "concurrently"

    mv = MonthlyRevenue()
    assert "CREATE MATERIALIZED VIEW monthly_revenue AS" in str(mv.create())
    refreshed = str(mv.refresh_op())
    assert "REFRESH MATERIALIZED VIEW" in refreshed
    assert "CONCURRENTLY" in refreshed  # refresh = "concurrently"


def test_database_function_create() -> None:
    class IncrementBalance(DatabaseFunction):
        name = "increment_balance"
        args = [("account_id", "bigint"), ("amount", "numeric")]
        returns = "numeric"
        language = "plpgsql"
        body = "BEGIN RETURN amount; END;"

    ddl = str(IncrementBalance().create())
    assert "CREATE OR REPLACE FUNCTION increment_balance" in ddl
    assert "account_id bigint" in ddl
    assert "RETURNS numeric" in ddl
