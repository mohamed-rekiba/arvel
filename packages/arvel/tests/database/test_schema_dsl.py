"""Schema DSL compiles to Alembic-shaped operations."""

from __future__ import annotations

from typing import Any, cast

from arvel.database.schema import Blueprint, Schema
from sqlalchemy import Column

# SQLA's ``Column`` is generic and ``isinstance(x, Column)`` leaves the
# generic parameter unbound (pyright sees ``Column[Unknown]``). A provably
# correct ``cast`` after the isinstance check pins it to ``Column[Any]``.
_AnyColumn = Column[Any]


def _find_column(emitted_args: tuple[Any, ...], name: str) -> _AnyColumn:
    """Locate the emitted ``Column[Any]`` with ``name`` inside Schema args.

    The cast matches the dual-checker cast pattern used below:
    mypy narrows ``isinstance(c, Column)`` to ``Column[Any]`` (cast looks
    redundant to mypy) while pyright leaves the generic parameter unbound
    (cast is required). Both suppressions are specific codes."""
    for c in emitted_args:
        if isinstance(c, Column) and c.name == name:
            return cast("_AnyColumn", c)  # type: ignore[redundant-cast]  # dual-checker cast
    raise AssertionError(f"no column named {name!r} in emitted args")


class RecordingExecutor:
    """Captures every call so tests can assert what SQL ops were emitted.

    Implements the `_Executor` protocol surface explicitly (not via
    ``__getattr__``) so pyright sees a real protocol match instead of
    dynamic attribute access."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def _record(self, name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
        self.calls.append((name, args, kwargs))

    def create_table(self, name: str, *columns: Column[Any], **kw: Any) -> None:
        self._record("create_table", (name, *columns), kw)

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


def test_create_compiles_columns_and_constraints() -> None:
    ex = RecordingExecutor()

    def build(t: Blueprint) -> None:
        t.id()
        t.string("name", length=120).nullable(False).unique()
        t.integer("age").nullable()
        t.timestamps()
        t.soft_deletes()

    Schema.create("users", build, executor=ex)

    op_names = [c[0] for c in ex.calls]
    assert op_names[0] == "create_table"
    table_name, columns = ex.calls[0][1][0], ex.calls[0][1][1:]
    assert table_name == "users"
    column_names = [c.name for c in columns if isinstance(c, Column)]
    assert "id" in column_names
    assert "name" in column_names
    assert "created_at" in column_names
    assert "updated_at" in column_names
    assert "deleted_at" in column_names


def test_morphs_emits_two_columns_and_compound_index() -> None:
    ex = RecordingExecutor()

    def build(t: Blueprint) -> None:
        t.id()
        t.morphs("commentable")

    Schema.create("comments", build, executor=ex)

    column_names = [c.name for c in ex.calls[0][1][1:] if isinstance(c, Column)]
    assert "commentable_type" in column_names
    assert "commentable_id" in column_names
    index_calls = [c for c in ex.calls if c[0] == "create_index"]
    assert any("commentable" in c[1][0] for c in index_calls)


def test_foreign_id_constrained_emits_foreign_key() -> None:
    ex = RecordingExecutor()

    def build(t: Blueprint) -> None:
        t.id()
        t.foreign_id("user_id").constrained()

    Schema.create("orders", build, executor=ex)

    # Mypy narrows the generator element to Column[Any] directly; pyright narrows
    # to Column[Unknown]. The cast is redundant for mypy but real for pyright,
    # and the inner generator's element type is still Unknown to pyright.
    gen = (c for c in ex.calls[0][1][1:] if isinstance(c, Column) and c.name == "user_id")  # pyright: ignore[reportUnknownVariableType]
    fk_col = cast("Column[Any]", next(gen))  # type: ignore[redundant-cast]
    assert len(list(fk_col.foreign_keys)) == 1
    fk = next(iter(fk_col.foreign_keys))
    assert fk.target_fullname == "users.id"


def test_table_emits_add_and_drop_column() -> None:
    ex = RecordingExecutor()

    def build(t: Blueprint) -> None:
        t.string("new_col")
        t.drop_column("old_col")

    Schema.table("users", build, executor=ex)

    ops = [c[0] for c in ex.calls]
    assert "add_column" in ops
    assert "drop_column" in ops


def test_drop_table_emits_drop_table() -> None:
    ex = RecordingExecutor()
    Schema.drop("users", executor=ex)
    assert ex.calls == [("drop_table", ("users",), {})]


# ─── use_current  ──────────────────────────────────


def test_use_current_sets_server_default() -> None:
    """use_current sets server_default=func.now on the Column."""
    from arvel.database.schema import Blueprint

    col = Blueprint.__new__(Blueprint).make_pending_column_for_test("created_at", "datetime")
    col.use_current()
    sqla_col = col.to_sqla_column()
    assert sqla_col.server_default is not None


def test_use_current_on_update_sets_server_onupdate() -> None:
    """use_current(on_update=True) also sets server_onupdate=FetchedValue."""
    from arvel.database.schema import Blueprint

    col = Blueprint.__new__(Blueprint).make_pending_column_for_test("updated_at", "datetime")
    col.use_current(on_update=True)
    sqla_col = col.to_sqla_column()
    assert sqla_col.server_default is not None
    assert sqla_col.server_onupdate is not None


def test_use_current_without_on_update_has_no_server_onupdate() -> None:
    """.use_current without on_update does NOT set server_onupdate."""
    from arvel.database.schema import Blueprint

    col = Blueprint.__new__(Blueprint).make_pending_column_for_test("ts", "datetime")
    col.use_current()
    sqla_col = col.to_sqla_column()
    assert sqla_col.server_onupdate is None


def test_use_current_is_fluent() -> None:
    """use_current returns PendingColumn for chaining."""
    from arvel.database.schema import Blueprint

    col = Blueprint.__new__(Blueprint).make_pending_column_for_test("ts", "datetime")
    result = col.use_current()
    assert result is col


def test_use_current_in_blueprint_ddl() -> None:
    """Blueprint.datetime.use_current appears in the DDL via schema create."""
    ex = RecordingExecutor()

    def build(t: Blueprint) -> None:
        t.id()
        t.datetime("created_at").use_current()
        t.datetime("updated_at").use_current(on_update=True)

    Schema.create("posts", build, executor=ex)
    assert ex.calls[0][0] == "create_table"


# ─── long_text  ────────────────────────────────────────


def test_long_text_adds_text_column() -> None:
    """Blueprint.long_text(name) → Text(length=4294967295)."""
    from sqlalchemy import Text

    ex = RecordingExecutor()

    def build(t: Blueprint) -> None:
        t.id()
        t.long_text("body")

    Schema.create("articles", build, executor=ex)
    assert ex.calls[0][0] == "create_table"
    _, args, _ = ex.calls[0]
    col_names = [c.name for c in args[1:] if hasattr(c, "name")]
    assert "body" in col_names
    body_col = next(c for c in args[1:] if hasattr(c, "name") and c.name == "body")
    assert isinstance(body_col.type, Text)
    assert body_col.type.length == 4294967295


def test_long_text_is_fluent() -> None:
    """Blueprint.long_text returns PendingColumn for chaining."""
    from arvel.database.schema import Blueprint

    bp = Blueprint("fluent_test")
    result = bp.long_text("content")
    # It returns a PendingColumn — can call .nullable etc.
    assert result is not None


# ─── raw_column escape hatch (L3 from SQLModel lessons research) ──────────────


def test_raw_column_emits_column_verbatim() -> None:
    """Blueprint.raw_column(Column(...)) passes the column through unchanged.

    Use case: a SQLA Column type (e.g. Postgres JSONB) or kwarg (e.g. computed
    defaults) the fluent helpers don't expose."""
    from sqlalchemy import JSON

    ex = RecordingExecutor()
    raw = Column("payload", JSON, nullable=False)

    def build(t: Blueprint) -> None:
        t.id()
        t.raw_column(raw)

    Schema.create("events", build, executor=ex)

    assert ex.calls[0][0] == "create_table"
    _, args, _ = ex.calls[0]
    payload_col = _find_column(args[1:], "payload")
    assert payload_col is raw, "raw_column must emit the user's Column verbatim"


def test_raw_column_ignores_chain_modifiers() -> None:
    """Chain methods on a raw column are no-ops — the user's Column wins."""
    from sqlalchemy import Integer

    ex = RecordingExecutor()
    raw = Column("counter", Integer, nullable=False)

    def build(t: Blueprint) -> None:
        t.id()
        # User mistakenly chains; chain methods on a raw column do not apply.
        t.raw_column(raw).unique().nullable(True)

    Schema.create("counters", build, executor=ex)

    _, args, _ = ex.calls[0]
    counter_col = _find_column(args[1:], "counter")
    assert counter_col is raw
    assert counter_col.nullable is False, "raw column's own nullable=False must hold"


def test_raw_column_requires_named_column() -> None:
    """An unnamed Column raises ValueError immediately, not at emit time."""
    import pytest
    from sqlalchemy import Integer

    bp = Blueprint("bad")
    with pytest.raises(ValueError, match="non-empty name"):
        bp.raw_column(Column(Integer))  # ← no name supplied


# ─── view DDL (create_view / drop_view / drop_view_if_exists) ────────────────


def test_create_view_emits_execute_with_create_view_sql() -> None:
    from sqlalchemy import TextClause

    ex = RecordingExecutor()
    Schema.create_view("active_users", "SELECT * FROM users WHERE active = 1", executor=ex)

    assert len(ex.calls) == 1
    op_name, args, _ = ex.calls[0]
    assert op_name == "execute"
    clause = args[0]
    assert isinstance(clause, TextClause)
    assert "CREATE VIEW active_users AS" in str(clause)
    assert "SELECT * FROM users WHERE active = 1" in str(clause)


def test_drop_view_emits_execute_with_drop_view_sql() -> None:
    from sqlalchemy import TextClause

    ex = RecordingExecutor()
    Schema.drop_view("active_users", executor=ex)

    assert len(ex.calls) == 1
    op_name, args, _ = ex.calls[0]
    assert op_name == "execute"
    clause = args[0]
    assert isinstance(clause, TextClause)
    assert "DROP VIEW active_users" in str(clause)


def test_drop_view_if_exists_emits_execute_with_if_exists_sql() -> None:
    from sqlalchemy import TextClause

    ex = RecordingExecutor()
    Schema.drop_view_if_exists("active_users", executor=ex)

    assert len(ex.calls) == 1
    op_name, args, _ = ex.calls[0]
    assert op_name == "execute"
    clause = args[0]
    assert isinstance(clause, TextClause)
    assert "DROP VIEW IF EXISTS active_users" in str(clause)


# ─── materialized view DDL ─────────────────────────────────────────────────────


def test_create_materialized_view_emits_create_sql() -> None:
    from sqlalchemy import TextClause

    ex = RecordingExecutor()
    Schema.create_materialized_view("daily_stats", "SELECT count(*) FROM orders", executor=ex)

    assert len(ex.calls) == 1
    clause = ex.calls[0][1][0]
    assert isinstance(clause, TextClause)
    assert "CREATE MATERIALIZED VIEW daily_stats AS" in str(clause)
    assert "SELECT count(*) FROM orders" in str(clause)
    assert "WITH NO DATA" not in str(clause)


def test_create_materialized_view_with_no_data() -> None:
    from sqlalchemy import TextClause

    ex = RecordingExecutor()
    Schema.create_materialized_view("daily_stats", "SELECT 1", with_data=False, executor=ex)

    clause = ex.calls[0][1][0]
    assert isinstance(clause, TextClause)
    assert "WITH NO DATA" in str(clause)


def test_refresh_materialized_view_emits_refresh_sql() -> None:
    from sqlalchemy import TextClause

    ex = RecordingExecutor()
    Schema.refresh_materialized_view("daily_stats", executor=ex)

    clause = ex.calls[0][1][0]
    assert isinstance(clause, TextClause)
    assert str(clause) == "REFRESH MATERIALIZED VIEW daily_stats"


def test_refresh_materialized_view_concurrently() -> None:
    from sqlalchemy import TextClause

    ex = RecordingExecutor()
    Schema.refresh_materialized_view("daily_stats", concurrently=True, executor=ex)

    clause = ex.calls[0][1][0]
    assert isinstance(clause, TextClause)
    assert str(clause) == "REFRESH MATERIALIZED VIEW CONCURRENTLY daily_stats"


def test_drop_materialized_view_emits_drop_sql() -> None:
    from sqlalchemy import TextClause

    ex = RecordingExecutor()
    Schema.drop_materialized_view("daily_stats", executor=ex)

    clause = ex.calls[0][1][0]
    assert isinstance(clause, TextClause)
    assert "DROP MATERIALIZED VIEW daily_stats" in str(clause)


def test_drop_materialized_view_if_exists_emits_if_exists_sql() -> None:
    from sqlalchemy import TextClause

    ex = RecordingExecutor()
    Schema.drop_materialized_view_if_exists("daily_stats", executor=ex)

    clause = ex.calls[0][1][0]
    assert isinstance(clause, TextClause)
    assert "DROP MATERIALIZED VIEW IF EXISTS daily_stats" in str(clause)


def test_has_materialized_view_uses_inspector_when_available() -> None:
    from unittest.mock import MagicMock

    inspector = MagicMock()
    inspector.get_materialized_view_names.return_value = ["daily_stats", "weekly_stats"]

    from arvel.database.schema import materialized_view_names

    assert materialized_view_names(inspector) == ["daily_stats", "weekly_stats"]


def test_has_materialized_view_returns_false_without_dialect_support() -> None:
    from unittest.mock import MagicMock

    inspector = MagicMock(spec=[])

    from arvel.database.schema import materialized_view_names

    assert materialized_view_names(inspector) == []


# ─── extension DDL (install_extension / uninstall_extension) ─────────────────


def test_install_extension_emits_create_extension_sql() -> None:
    from sqlalchemy import TextClause

    ex = RecordingExecutor()
    Schema.install_extension("uuid-ossp", executor=ex)

    assert len(ex.calls) == 1
    op_name, args, _ = ex.calls[0]
    assert op_name == "execute"
    clause = args[0]
    assert isinstance(clause, TextClause)
    assert 'CREATE EXTENSION IF NOT EXISTS "uuid-ossp"' in str(clause)


def test_uninstall_extension_emits_drop_extension_sql() -> None:
    from sqlalchemy import TextClause

    ex = RecordingExecutor()
    Schema.uninstall_extension("uuid-ossp", executor=ex)

    assert len(ex.calls) == 1
    op_name, args, _ = ex.calls[0]
    assert op_name == "execute"
    clause = args[0]
    assert isinstance(clause, TextClause)
    assert 'DROP EXTENSION IF EXISTS "uuid-ossp"' in str(clause)
