"""Schema DSL: partial indexes, unique=, NULLS NOT DISTINCT, soft_deletes index."""

from __future__ import annotations

from typing import Any

import pytest
from arvel.database.schema import Blueprint, Schema
from sqlalchemy import Column, text
from sqlalchemy.schema import UniqueConstraint

# ─── Shared recording executor ────────────────────────────────────────────────


class _Rec:
    """Minimal recording executor for schema DSL tests."""

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

    def index_calls(self) -> list[dict[str, Any]]:
        return [
            {"name": args[0], "table": args[1], "cols": args[2], **kw}
            for op, args, kw in self.calls
            if op == "create_index"
        ]

    def unique_constraints(self) -> list[UniqueConstraint]:
        result: list[UniqueConstraint] = []
        for op, args, _kw in self.calls:
            if op == "create_table":
                result.extend(a for a in args if isinstance(a, UniqueConstraint))
        return result


# ─── where= forwarded as postgresql_where ──────────────────────────


def test_index_where_forwarded_as_postgresql_where() -> None:
    """where= predicate forwarded to create_index."""
    ex = _Rec()
    predicate = text("deleted_at IS NULL")

    def build(t: Blueprint) -> None:
        t.id()
        t.index(["deleted_at"], name="idx_deleted", where=predicate)

    Schema.create("items", build, executor=ex)

    idx_calls = ex.index_calls()
    idx = next(c for c in idx_calls if c["name"] == "idx_deleted")
    assert "postgresql_where" in idx
    assert idx["postgresql_where"] is predicate


# ─── where=None → no postgresql_where kwarg ───────────────────────


def test_index_no_where_emits_no_postgresql_where() -> None:
    """Default where=None produces no postgresql_where kwarg."""
    ex = _Rec()

    def build(t: Blueprint) -> None:
        t.id()
        t.index(["status"], name="idx_status")

    Schema.create("orders", build, executor=ex)

    idx = next(c for c in ex.index_calls() if c["name"] == "idx_status")
    assert "postgresql_where" not in idx


# ─── unique=True on index ────────────────────────────────────────


def test_index_unique_true_forwarded() -> None:
    """unique=True on Blueprint.index → create_index unique=True."""
    ex = _Rec()

    def build(t: Blueprint) -> None:
        t.id()
        t.index(["slug"], name="idx_slug_unique", unique=True)

    Schema.create("posts", build, executor=ex)

    idx = next(c for c in ex.index_calls() if c["name"] == "idx_slug_unique")
    assert idx.get("unique") is True


# ─── unique=True + where= combined ─────────────────────────────────


def test_index_unique_with_where_combined() -> None:
    """unique=True and where= can be combined in one call."""
    ex = _Rec()
    predicate = text("status = 'pending'")

    def build(t: Blueprint) -> None:
        t.id()
        t.index(["user_id"], name="one_pending_per_user", unique=True, where=predicate)

    Schema.create("orders", build, executor=ex)

    idx = next(c for c in ex.index_calls() if c["name"] == "one_pending_per_user")
    assert idx.get("unique") is True
    assert idx.get("postgresql_where") is predicate


# ─── nulls_not_distinct=True ──────────────────────────────────────


def test_unique_nulls_not_distinct_true() -> None:
    """nulls_not_distinct=True → postgresql_nulls_not_distinct=True on constraint."""
    ex = _Rec()

    def build(t: Blueprint) -> None:
        t.id()
        t.string("invite_code").nullable()
        t.unique(["invite_code"], name="invite_code_uq", nulls_not_distinct=True)

    Schema.create("invites", build, executor=ex)

    constraints = ex.unique_constraints()
    uc = next(c for c in constraints if c.name == "invite_code_uq")
    assert uc.dialect_kwargs.get("postgresql_nulls_not_distinct") is True


# ─── nulls_not_distinct=False ─────────────────────────────────────


def test_unique_nulls_not_distinct_false() -> None:
    """nulls_not_distinct=False → postgresql_nulls_not_distinct=False."""
    ex = _Rec()

    def build(t: Blueprint) -> None:
        t.id()
        t.string("slug").nullable()
        t.unique(["slug"], name="slug_uq", nulls_not_distinct=False)

    Schema.create("posts", build, executor=ex)

    constraints = ex.unique_constraints()
    uc = next(c for c in constraints if c.name == "slug_uq")
    assert uc.dialect_kwargs.get("postgresql_nulls_not_distinct") is False


# ─── nulls_not_distinct=None (default) → no kwarg ─────────────────


def test_unique_nulls_not_distinct_none_emits_no_kwarg() -> None:
    """Default nulls_not_distinct=None → postgresql_nulls_not_distinct stays None.

    SQLAlchemy's _DialectArgView always exposes all dialect kwargs; a key that was not
    explicitly set has value None. We assert None, not key absence."""
    ex = _Rec()

    def build(t: Blueprint) -> None:
        t.id()
        t.string("email")
        t.unique(["email"], name="email_uq")

    Schema.create("users", build, executor=ex)

    constraints = ex.unique_constraints()
    uc = next(c for c in constraints if c.name == "email_uq")
    assert uc.dialect_kwargs.get("postgresql_nulls_not_distinct") is None


# ─── regression — existing callers unaffected ─────────────────────


def test_existing_index_call_no_regression() -> None:
    """Blueprint.index with no new params behaves identically to before."""
    ex = _Rec()

    def build(t: Blueprint) -> None:
        t.id()
        t.string("category")
        t.index(["category"], name="idx_category")

    Schema.create("items", build, executor=ex)

    idx = next(c for c in ex.index_calls() if c["name"] == "idx_category")
    assert idx["cols"] == ["category"]
    assert idx.get("unique") is False
    assert "postgresql_where" not in idx


def test_existing_unique_call_no_regression() -> None:
    """(unique): Blueprint.unique with no new params behaves identically to before."""
    ex = _Rec()

    def build(t: Blueprint) -> None:
        t.id()
        t.string("email")
        t.unique(["email"], name="users_email_unique")

    Schema.create("users", build, executor=ex)

    constraints = ex.unique_constraints()
    uc = next(c for c in constraints if c.name == "users_email_unique")
    # nulls_not_distinct not explicitly set → dialect_kwargs returns None (SA default)
    assert uc.dialect_kwargs.get("postgresql_nulls_not_distinct") is None


# ─── Items migration partial index shape ──────────────────────────────────────


def test_items_migration_deleted_at_index_is_partial() -> None:
    """(migration): soft_deletes auto-emits the partial index; composite is manual."""
    ex = _Rec()

    def build(t: Blueprint) -> None:
        t.id()
        t.foreign_id("user_id").nullable(False)
        t.string("title", length=200).nullable(False)
        t.text("description").nullable()
        t.enum("category", values=["note", "task", "idea", "link"]).nullable(False)
        t.json("tags").nullable()
        t.timestamps()
        t.soft_deletes()
        t.index(["user_id", "created_at"], name="items_user_created_idx")
        t.index(
            ["category", "deleted_at"],
            name="items_category_deleted_at_idx",
            where="deleted_at IS NULL",
        )

    Schema.create("items", build, executor=ex)

    idx_calls = {c["name"]: c for c in ex.index_calls()}
    # auto-emitted by soft_deletes
    assert "postgresql_where" in idx_calls["ix_items_deleted_at_active"]
    # manual composite partial index
    assert "postgresql_where" in idx_calls["items_category_deleted_at_idx"]
    # plain user/created index must NOT have a predicate
    assert "postgresql_where" not in idx_calls["items_user_created_idx"]


# ─── Fluency / type-safety spot-checks ───────────────────────────────────────


@pytest.mark.parametrize(
    ("where_val", "expect_key"),
    [
        (text("col IS NULL"), True),
        (None, False),
    ],
)
def test_index_where_parametrized(
    where_val: Any,
    expect_key: bool,
) -> None:
    """Parametrized: where= present ↔ postgresql_where in kwargs."""
    ex = _Rec()

    def build(t: Blueprint) -> None:
        t.id()
        kwargs: dict[str, Any] = {"name": "idx_test"}
        if where_val is not None:
            kwargs["where"] = where_val
        t.index(["col"], **kwargs)

    Schema.create("t", build, executor=ex)
    idx = ex.index_calls()[0]
    assert ("postgresql_where" in idx) is expect_key


# ─── soft_deletes partial index ────────────────────────────


def test_soft_deletes_auto_emits_partial_index() -> None:
    """soft_deletes creates a partial index by default."""
    ex = _Rec()

    def build(t: Blueprint) -> None:
        t.id()
        t.soft_deletes()

    Schema.create("posts", build, executor=ex)

    idx_calls = {c["name"]: c for c in ex.index_calls()}
    assert "ix_posts_deleted_at_active" in idx_calls
    idx = idx_calls["ix_posts_deleted_at_active"]
    assert "postgresql_where" in idx
    assert str(idx["postgresql_where"]) == "deleted_at IS NULL"


def test_soft_deletes_index_false_emits_no_index() -> None:
    """soft_deletes(index=False) skips the partial index."""
    ex = _Rec()

    def build(t: Blueprint) -> None:
        t.id()
        t.soft_deletes(index=False)

    Schema.create("posts", build, executor=ex)

    names = [c["name"] for c in ex.index_calls()]
    assert "ix_posts_deleted_at_active" not in names


def test_soft_deletes_custom_column_name_index() -> None:
    """Custom column name is reflected in the auto-generated index name."""
    ex = _Rec()

    def build(t: Blueprint) -> None:
        t.id()
        t.soft_deletes(name="archived_at")

    Schema.create("orders", build, executor=ex)

    idx_calls = {c["name"]: c for c in ex.index_calls()}
    assert "ix_orders_archived_at_active" in idx_calls
    idx = idx_calls["ix_orders_archived_at_active"]
    assert str(idx["postgresql_where"]) == "archived_at IS NULL"
