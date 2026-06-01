"""Blueprint.tsvector() and Blueprint.gin_index()."""

from __future__ import annotations

from typing import Any, cast

from arvel.database.schema import Blueprint, Schema
from sqlalchemy import Column


class _Rec:
    """Records executor calls for assertion."""

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


# ── Blueprint.tsvector ─────────────────────────────────────────────


def test_tsvector_column_added_to_blueprint() -> None:
    """Given tsvector is called, the Blueprint records a column named correctly."""
    ex = _Rec()

    def build(t: Blueprint) -> None:
        t.id()
        t.tsvector("search_vector")

    Schema.create("posts", build, executor=ex)
    ct_call = next((c for c in ex.calls if c[0] == "create_table"), None)
    assert ct_call is not None, "create_table was not called"
    col_names = [c.name for c in ct_call[1][1:] if isinstance(c, Column)]
    assert "search_vector" in col_names


def test_tsvector_column_is_nullable_by_default() -> None:
    """tsvector without chaining behaves like other column helpers — nullable by default."""
    ex = _Rec()

    def build(t: Blueprint) -> None:
        t.tsvector("search_vector")

    Schema.create("posts", build, executor=ex)
    ct_call = next(c for c in ex.calls if c[0] == "create_table")
    columns = cast("tuple[Column[Any], ...]", ct_call[1][1:])
    col = next(c for c in columns if c.name == "search_vector")
    assert col.nullable is True


def test_tsvector_column_nullable_chain() -> None:
    """Given .nullable is chained, the column becomes nullable."""
    ex = _Rec()

    def build(t: Blueprint) -> None:
        t.tsvector("search_vector").nullable()

    Schema.create("posts", build, executor=ex)
    ct_call = next(c for c in ex.calls if c[0] == "create_table")
    columns = cast("tuple[Column[Any], ...]", ct_call[1][1:])
    col = next(c for c in columns if c.name == "search_vector")
    assert col.nullable is True


def test_tsvector_column_type_is_postgresql_tsvector_on_pg_dialect() -> None:
    """tsvector emits TSVECTOR DDL when compiled with the postgresql dialect."""
    from arvel.database.schema import Blueprint
    from sqlalchemy import create_mock_engine, make_url

    bp = Blueprint(table_name="posts")
    sqla_col = bp.tsvector("search_vector").to_sqla_column()

    def _noop(*_: Any, **__: Any) -> None:
        return None

    dialect = create_mock_engine(make_url("postgresql+psycopg2://"), _noop).dialect
    assert sqla_col.type.compile(dialect=dialect).upper() == "TSVECTOR"


def test_tsvector_column_type_degrades_to_text_on_sqlite() -> None:
    """tsvector falls back to TEXT on non-PostgreSQL dialects (SQLite CI path)."""
    from arvel.database.schema import Blueprint
    from sqlalchemy.dialects import sqlite as sq

    bp = Blueprint(table_name="posts")
    sqla_col = bp.tsvector("search_vector").to_sqla_column()
    assert sqla_col.type.compile(dialect=sq.dialect()).upper() == "TEXT"


# ── Blueprint.gin_index ────────────────────────────────────────────


def test_gin_index_emits_create_index_with_postgresql_using_gin() -> None:
    """gin_index calls create_index with postgresql_using='gin' in kwargs."""
    ex = _Rec()

    def build(t: Blueprint) -> None:
        t.id()
        t.tsvector("search_vector")
        t.gin_index("posts", "search_vector")

    Schema.create("posts", build, executor=ex)
    idx_calls = [c for c in ex.calls if c[0] == "create_index"]
    assert idx_calls, "create_index was not called"
    gin_call = next(
        (c for c in idx_calls if c[2].get("postgresql_using") == "gin"),
        None,
    )
    assert gin_call is not None, "No create_index call had postgresql_using='gin'"


def test_gin_index_covers_the_correct_columns() -> None:
    """gin_index('posts', 'search_vector') covers exactly ['search_vector']."""
    ex = _Rec()

    def build(t: Blueprint) -> None:
        t.tsvector("search_vector")
        t.gin_index("posts", "search_vector")

    Schema.create("posts", build, executor=ex)
    idx_calls = [c for c in ex.calls if c[0] == "create_index"]
    gin_call = next(c for c in idx_calls if c[2].get("postgresql_using") == "gin")
    assert "search_vector" in gin_call[1][2]


def test_gin_index_multi_column() -> None:
    """gin_index with two columns covers both in the index."""
    ex = _Rec()

    def build(t: Blueprint) -> None:
        t.tsvector("search_vector")
        t.string("tags")
        t.gin_index("posts", "search_vector", "tags")

    Schema.create("posts", build, executor=ex)
    idx_calls = [c for c in ex.calls if c[0] == "create_index"]
    gin_call = next(c for c in idx_calls if c[2].get("postgresql_using") == "gin")
    assert "search_vector" in gin_call[1][2]
    assert "tags" in gin_call[1][2]


def test_gin_index_does_not_affect_regular_indexes() -> None:
    """A regular index and a gin_index coexist without conflict."""
    ex = _Rec()

    def build(t: Blueprint) -> None:
        t.string("title")
        t.tsvector("search_vector")
        t.index("title")
        t.gin_index("posts", "search_vector")

    Schema.create("posts", build, executor=ex)
    idx_calls = [c for c in ex.calls if c[0] == "create_index"]
    assert len(idx_calls) == 2
    gin_calls = [c for c in idx_calls if c[2].get("postgresql_using") == "gin"]
    regular_calls = [c for c in idx_calls if "postgresql_using" not in c[2]]
    assert len(gin_calls) == 1
    assert len(regular_calls) == 1


def test_gin_index_auto_generated_name() -> None:
    """gin_index generates a deterministic name in the form 'gin_{table}_{cols}'."""
    ex = _Rec()

    def build(t: Blueprint) -> None:
        t.tsvector("search_vector")
        t.gin_index("posts", "search_vector")

    Schema.create("posts", build, executor=ex)
    idx_calls = [c for c in ex.calls if c[0] == "create_index"]
    gin_call = next(c for c in idx_calls if c[2].get("postgresql_using") == "gin")
    idx_name: str = gin_call[1][0]
    assert "gin" in idx_name
    assert "search_vector" in idx_name
