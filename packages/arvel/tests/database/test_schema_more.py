"""Additional Schema DSL coverage — alter, drop_if_exists, rename, more column types."""

from __future__ import annotations

from typing import Any

import pytest
from arvel.database import schema as schema_module
from arvel.database.schema import Blueprint, ForeignKeyAction, IdType, Schema
from sqlalchemy import Column, String, create_engine, text
from sqlalchemy.ext.asyncio import AsyncEngine


class _Rec:
    """Records every executor call.

    Implements the six `_Executor` protocol methods explicitly so pyright
    sees a concrete protocol match, and falls back to `__getattr__` for
    non-protocol methods like `rename_table` that Schema.rename duck-types."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def _rec(self, name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
        self.calls.append((name, args, kwargs))

    def create_table(self, name: str, *columns: Column[Any], **kw: Any) -> None:
        self._rec("create_table", (name, *columns), kw)

    def drop_table(self, name: str, **kw: Any) -> None:
        self._rec("drop_table", (name,), kw)

    def add_column(self, table_name: str, column: Column[Any], **kw: Any) -> None:
        self._rec("add_column", (table_name, column), kw)

    def drop_column(self, table_name: str, column_name: str, **kw: Any) -> None:
        self._rec("drop_column", (table_name, column_name), kw)

    def create_index(self, name: str, table: str, columns: list[str], **kw: Any) -> None:
        self._rec("create_index", (name, table, columns), kw)

    def drop_index(self, name: str, table_name: str | None = None, **kw: Any) -> None:
        self._rec("drop_index", (name, table_name), kw)

    def execute(self, clause: Any, **kw: Any) -> None:
        self._rec("execute", (clause,), kw)

    def __getattr__(self, name: str) -> Any:
        # Fallback for non-protocol methods Schema duck-types onto the executor
        # (currently just `rename_table`). Keep pyright's view of explicit
        # protocol methods above the `__getattr__` so they take precedence.
        def _fallback(*args: Any, **kwargs: Any) -> None:
            self._rec(name, args, kwargs)

        return _fallback


def test_table_drops_index() -> None:
    rec = _Rec()

    def build(t: Blueprint) -> None:
        t.drop_index("ix_widgets_legacy")

    Schema.table("widgets", build, executor=rec)
    assert any(c[0] == "drop_index" for c in rec.calls)


def test_drop_if_exists_calls_drop_table() -> None:
    rec = _Rec()
    Schema.drop_if_exists("widgets", executor=rec)
    assert rec.calls == [("drop_table", ("widgets",), {})]


def test_rename_calls_executor_rename() -> None:
    rec = _Rec()
    Schema.rename("old", "new", executor=rec)
    assert any(c[0] == "rename_table" for c in rec.calls)


def test_rename_without_executor_support_raises() -> None:
    class NoRename:
        # Implements just enough for the type check but no rename_table.
        def create_table(self, *a: Any, **k: Any) -> None:
            pass

        def drop_table(self, *a: Any, **k: Any) -> None:
            pass

        def add_column(self, *a: Any, **k: Any) -> None:
            pass

        def drop_column(self, *a: Any, **k: Any) -> None:
            pass

        def create_index(self, *a: Any, **k: Any) -> None:
            pass

        def drop_index(self, *a: Any, **k: Any) -> None:
            pass

        def execute(self, *a: Any, **k: Any) -> None:
            pass

    with pytest.raises(NotImplementedError):
        Schema.rename("a", "b", executor=NoRename())


def test_explicit_unique_constraint_named() -> None:
    rec = _Rec()

    def build(t: Blueprint) -> None:
        t.id()
        t.string("email")
        t.unique(["email"], name="uq_users_email")

    Schema.create("users", build, executor=rec)
    create_call = next(c for c in rec.calls if c[0] == "create_table")
    constraint_names = [getattr(c, "name", None) for c in create_call[1] if hasattr(c, "name")]
    assert "uq_users_email" in constraint_names


def test_explicit_index_chainable() -> None:
    rec = _Rec()

    def build(t: Blueprint) -> None:
        t.id()
        t.string("name")
        t.index("name")

    Schema.create("u", build, executor=rec)
    idx = [c for c in rec.calls if c[0] == "create_index"]
    assert len(idx) >= 1
    assert idx[0][1][2] == ["name"]


def test_more_column_types_compile() -> None:
    rec = _Rec()

    def build(t: Blueprint) -> None:
        t.id()
        t.text("body")
        t.boolean("flag")
        t.float("score")
        t.decimal("price", precision=8, scale=4)
        t.datetime("when")
        t.json("payload")
        t.binary("blob")
        t.big_integer("counter")
        t.integer("count")

    Schema.create("misc", build, executor=rec)
    create_call = next(c for c in rec.calls if c[0] == "create_table")
    column_names = [c.name for c in create_call[1][1:] if hasattr(c, "name")]
    for expected in (
        "body",
        "flag",
        "score",
        "price",
        "when",
        "payload",
        "blob",
        "counter",
        "count",
    ):
        assert expected in column_names


def test_blueprint_big_integer_emits_bigint() -> None:
    """t.big_integer must produce BIGINT, not INTEGER.

    The model-layer big_integer() already maps to BigInteger; this is the
    migration-layer mirror. When it silently emitted INTEGER, columns like
    media.size and sessions.user_id were 32-bit on Postgres/MySQL — drifting
    from their BIGINT models and overflowing past ~2.1B.
    """
    from sqlalchemy import BigInteger, Integer

    rec = _Rec()

    def build(t: Blueprint) -> None:
        t.id()
        t.big_integer("counter")
        t.integer("small")

    Schema.create("bigints", build, executor=rec)
    create_call = next(c for c in rec.calls if c[0] == "create_table")
    cols = {c.name: c for c in create_call[1][1:] if hasattr(c, "name")}
    assert isinstance(cols["counter"].type, BigInteger)
    # Regular integer stays 32-bit (BigInteger subclasses Integer, so check the
    # negative case explicitly to prove they're distinct).
    assert not isinstance(cols["small"].type, BigInteger)
    assert isinstance(cols["small"].type, Integer)


def test_foreign_id_on_delete() -> None:
    rec = _Rec()

    def build(t: Blueprint) -> None:
        t.id()
        t.foreign_id("user_id").constrained().on_delete(ForeignKeyAction.CASCADE)

    Schema.create("orders", build, executor=rec)
    create_call = next(c for c in rec.calls if c[0] == "create_table")
    fk_col = next(c for c in create_call[1][1:] if hasattr(c, "name") and c.name == "user_id")
    fk = next(iter(fk_col.foreign_keys))
    assert fk.ondelete == "CASCADE"


def test_foreign_id_shorthands_compile_fk_actions() -> None:
    rec = _Rec()

    def build(t: Blueprint) -> None:
        t.id()
        t.foreign_id("user_id").constrained("users").cascade()
        t.foreign_id("group_id").constrained("groups").restrict()
        t.foreign_id("team_id").constrained("teams").set_null()

    Schema.create("memberships", build, executor=rec)
    create_call = next(c for c in rec.calls if c[0] == "create_table")
    columns = {c.name: c for c in create_call[1][1:] if hasattr(c, "name")}

    user_fk = next(iter(columns["user_id"].foreign_keys))
    group_fk = next(iter(columns["group_id"].foreign_keys))
    team_fk = next(iter(columns["team_id"].foreign_keys))
    assert user_fk.ondelete == "CASCADE"
    assert user_fk.onupdate == "CASCADE"
    assert group_fk.ondelete == "RESTRICT"
    assert group_fk.onupdate == "RESTRICT"
    assert team_fk.ondelete == "SET NULL"


def test_blueprint_uuid_id_disables_autoincrement() -> None:
    column = Blueprint("uuids").id(id_type=IdType.UUID)
    assert column.autoincrement_value is False


def test_medium_text_and_auto_constrained_table() -> None:
    rec = _Rec()

    def build(t: Blueprint) -> None:
        t.id()
        t.medium_text("body")
        t.foreign_id("order_id").constrained()

    Schema.create("notes", build, executor=rec)
    create_call = next(c for c in rec.calls if c[0] == "create_table")
    columns = {c.name: c for c in create_call[1][1:] if hasattr(c, "name")}
    assert getattr(columns["body"].type, "length", None) == 16777215
    order_fk = next(iter(columns["order_id"].foreign_keys))
    assert order_fk.target_fullname == "orders.id"


def test_schema_table_rename_and_modify_column() -> None:
    rec = _Rec()

    def build(t: Blueprint) -> None:
        t.rename_column("old_name", "new_name")
        t.modify_column("status", nullable=False, type_=String(50))

    Schema.table("widgets", build, executor=rec)

    assert ("alter_column", ("widgets", "old_name"), {"new_column_name": "new_name"}) in rec.calls
    assert any(
        call[0] == "alter_column"
        and call[1] == ("widgets", "status")
        and call[2]["nullable"] is False
        and isinstance(call[2]["type_"], String)
        for call in rec.calls
    )


async def test_schema_introspection_without_active_session_returns_empty() -> None:
    assert await Schema.has_table("schema_active") is False
    assert await Schema.has_column("schema_active", "name") is False
    assert await Schema.get_columns("schema_active") == []


def test_schema_sql_and_view_helpers_emit_statements() -> None:
    rec = _Rec()

    Schema.run_sql("SELECT 1", executor=rec)
    Schema.install_extension("pg_trgm", executor=rec)
    Schema.uninstall_extension("pg_trgm", executor=rec)
    Schema.create_view("active_users", "SELECT 1", executor=rec)
    Schema.drop_view("active_users", executor=rec)
    Schema.drop_view_if_exists("active_users", executor=rec)
    Schema.create_materialized_view("active_users_mv", "SELECT 1", with_data=False, executor=rec)
    Schema.refresh_materialized_view("active_users_mv", concurrently=True, executor=rec)
    Schema.drop_materialized_view("active_users_mv", executor=rec)
    Schema.drop_materialized_view_if_exists("active_users_mv", executor=rec)

    sql = [str(call[1][0]) for call in rec.calls if call[0] == "execute"]
    assert "SELECT 1" in sql[0]
    assert 'CREATE EXTENSION IF NOT EXISTS "pg_trgm"' in sql[1]
    assert 'DROP EXTENSION IF EXISTS "pg_trgm"' in sql[2]
    assert "CREATE VIEW active_users AS SELECT 1" in sql[3]
    assert "DROP VIEW active_users" in sql[4]
    assert "DROP VIEW IF EXISTS active_users" in sql[5]
    assert "WITH NO DATA" in sql[6]
    assert "REFRESH MATERIALIZED VIEW CONCURRENTLY active_users_mv" in sql[7]
    assert "DROP MATERIALIZED VIEW active_users_mv" in sql[8]
    assert "DROP MATERIALIZED VIEW IF EXISTS active_users_mv" in sql[9]


async def test_schema_materialized_view_checks_return_false_for_sqlite(
    engine: AsyncEngine,
) -> None:
    assert await Schema.has_materialized_view("missing_mv") is False


async def test_schema_sync_engine_introspection_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE sync_table (id integer, name varchar)"))
            conn.execute(text("CREATE VIEW sync_view AS SELECT id FROM sync_table"))

        def materialized_names(inspector: object) -> list[str]:
            return ["sync_mv"]

        monkeypatch.setattr(schema_module, "materialized_view_names", materialized_names)

        assert await Schema.has_table(engine, "sync_table") is True
        assert await Schema.has_column(engine, "sync_table", "name") is True
        assert [column["name"] for column in await Schema.get_columns(engine, "sync_table")] == [
            "id",
            "name",
        ]
        assert await Schema.has_view(engine, "sync_view") is True
        assert await Schema.has_materialized_view(engine, "sync_mv") is True
    finally:
        engine.dispose()


def test_column_default_value() -> None:
    rec = _Rec()

    def build(t: Blueprint) -> None:
        t.id()
        t.string("status").default("active")

    Schema.create("things", build, executor=rec)
    create_call = next(c for c in rec.calls if c[0] == "create_table")
    status_col = next(c for c in create_call[1][1:] if c.name == "status")
    assert status_col.default.arg == "active"
