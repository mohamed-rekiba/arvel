"""Blueprint.jsonb and JsonB TypeDecorator tests.

Fail until ``Blueprint.jsonb`` and ``JsonB`` exist in ``arvel.database.schema``."""

from __future__ import annotations

from typing import Any, cast

import pytest
from arvel.database.schema import Blueprint, Schema
from sqlalchemy import Column

# ── Shared test infra (mirrors test_schema_dsl.py) ───────────────────────────


class _RecordingExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def _record(self, name: str, args: tuple[Any, ...], kw: dict[str, Any]) -> None:
        self.calls.append((name, args, kw))

    def create_table(self, name: str, *cols: Column[Any], **kw: Any) -> None:
        self._record("create_table", (name, *cols), kw)

    def drop_table(self, name: str, **kw: Any) -> None:
        self._record("drop_table", (name,), kw)

    def add_column(self, table_name: str, column: Column[Any], **kw: Any) -> None:
        self._record("add_column", (table_name, column), kw)

    def drop_column(self, table_name: str, column_name: str, **kw: Any) -> None:
        self._record("drop_column", (table_name, column_name), kw)

    def create_index(self, name: str, table: str, columns: list[str], **kw: Any) -> None:
        self._record("create_index", (name, table, columns), kw)

    def drop_index(self, name: str, table_name: str | None = None, **kw: Any) -> None:
        self._record("drop_index", (name, table_name), kw)

    def execute(self, clause: Any, **kw: Any) -> None:
        self._record("execute", (clause,), kw)


def _find_column(emitted_args: tuple[Any, ...], name: str) -> Column[Any]:
    for c in emitted_args:
        if isinstance(c, Column) and c.name == name:
            return cast("Column[Any]", c)  # type: ignore[redundant-cast]
    raise AssertionError(f"no column named {name!r} in emitted args")


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_jsonb_method_exists_on_blueprint() -> None:
    """Blueprint exposes a jsonb method."""
    assert hasattr(Blueprint, "jsonb"), "Blueprint.jsonb() not found"
    assert callable(Blueprint.jsonb)


def test_jsonb_returns_pending_column() -> None:
    """jsonb returns a PendingColumn with the standard chain API."""
    from arvel.database.schema import PendingColumn

    bp = Blueprint(table_name="t")
    col = bp.jsonb("data")

    assert isinstance(col, PendingColumn)
    assert col.name == "data"


def test_jsonb_emitted_to_create_table() -> None:
    """Schema.create emits the jsonb column into create_table call."""
    ex = _RecordingExecutor()

    def build(t: Blueprint) -> None:
        t.id()
        t.jsonb("payload")
        t.timestamps()

    Schema.create("orders", build, executor=ex)

    assert ex.calls[0][0] == "create_table"
    col = _find_column(ex.calls[0][1][1:], "payload")
    assert col is not None


def test_jsonb_type_is_jsonb_on_postgresql() -> None:
    """JsonB resolves to JSONB on PostgreSQL dialect."""
    from arvel.database.schema import JsonB
    from sqlalchemy.dialects.postgresql import dialect as pg_dialect

    jb = JsonB()
    pg = pg_dialect()  # type: ignore[no-untyped-call]  # SQLAlchemy dialect not typed
    impl = jb.load_dialect_impl(pg)

    from sqlalchemy.dialects.postgresql import JSONB

    assert isinstance(impl, JSONB)


def test_jsonb_type_degrades_to_json_on_sqlite() -> None:
    """JsonB degrades to JSON on non-PG dialects without raising."""
    from arvel.database.schema import JsonB
    from sqlalchemy import JSON
    from sqlalchemy.dialects.sqlite import dialect as sqlite_dialect

    jb = JsonB()
    sq = sqlite_dialect()
    impl = jb.load_dialect_impl(sq)

    assert isinstance(impl, JSON)


def test_jsonb_supports_nullable_chain() -> None:
    """chain modifiers work on jsonb columns."""
    bp = Blueprint(table_name="t")
    col = bp.jsonb("meta").nullable(False)
    sqla_col = col.to_sqla_column()

    assert sqla_col.nullable is False


def test_jsonb_supports_unique_chain() -> None:
    """unique works on jsonb columns."""
    bp = Blueprint(table_name="t")
    col = bp.jsonb("key").unique()
    sqla_col = col.to_sqla_column()

    assert sqla_col.unique is True


def test_jsonb_does_not_affect_json() -> None:
    """Blueprint.json still emits JSON (not JSONB) — no regression."""
    from sqlalchemy import JSON

    bp = Blueprint(table_name="t")
    col = bp.json("meta")
    sqla_col = col.to_sqla_column()

    assert isinstance(sqla_col.type, JSON)

    # Ensure it's NOT an instance of JsonB (which would be a different class)
    from arvel.database.schema import JsonB

    assert not isinstance(sqla_col.type, JsonB)  # type: ignore[unreachable]  # mypy can't see JSON → JsonB subtype at runtime


def test_jsonb_composable_with_gin_index() -> None:
    """gin_index can be declared alongside a jsonb column."""
    ex = _RecordingExecutor()

    def build(t: Blueprint) -> None:
        t.id()
        t.jsonb("data")
        t.gin_index("products", "data")

    Schema.create("products", build, executor=ex)

    # Should produce: create_table + create_index (GIN)
    call_names = [c[0] for c in ex.calls]
    assert "create_table" in call_names
    assert "create_index" in call_names

    gin_call = next(c for c in ex.calls if c[0] == "create_index")
    assert gin_call[2].get("postgresql_using") == "gin"


@pytest.mark.parametrize(
    "method",
    ["jsonb"],
)
def test_jsonb_is_exported_from_arvel_database(method: str) -> None:
    """Blueprint public surface includes jsonb."""
    assert hasattr(Blueprint, method), f"Blueprint.{method} not exported"
