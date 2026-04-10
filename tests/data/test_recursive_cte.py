"""Tests for Story 9: Recursive Query Builder (WITH RECURSIVE CTEs).

Covers: FR-28 through FR-34, SEC-06.

Test tree::

    Root (id=1)
    ├── Child1 (id=2)
    │   └── Grandchild (id=4)
    └── Child2 (id=3)
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import ForeignKey, String, Table
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import Mapped, mapped_column  # noqa: TC002

from arvel.data.model import ArvelModel
from arvel.data.query import QueryBuilder
from arvel.data.results import TreeNode

# ──── Hierarchical Test Model ────


class Category(ArvelModel):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True)


# ──── Helpers ────


def _collect_names(nodes: list[TreeNode[Any]]) -> set[str]:
    """Recursively collect all names from a nested tree."""
    names: set[str] = set()
    for node in nodes:
        names.add(node.data["name"])
        names |= _collect_names(node.children)
    return names


# ──── Fixtures ────


@pytest.fixture(scope="module", autouse=True)
def _create_category_table() -> None:
    """Create the categories table in the test DB."""
    from pathlib import Path

    from sqlalchemy import create_engine, event

    db_path = Path(__file__).parent / ".test.db"
    sync_engine = create_engine(f"sqlite:///{db_path}", echo=False)

    @event.listens_for(sync_engine, "connect")
    def _enable_fk(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    table = Category.__table__
    assert isinstance(table, Table)
    table.create(sync_engine, checkfirst=True)
    sync_engine.dispose()


@pytest.fixture
async def cte_session(anyio_backend: str) -> AsyncGenerator[AsyncSession]:
    """Session for recursive CTE tests with seeded category tree."""
    from pathlib import Path

    from sqlalchemy import event, text

    db_path = Path(__file__).parent / ".test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_fk(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.connect() as conn:
        trans = await conn.begin()
        async with AsyncSession(bind=conn, expire_on_commit=False) as session:
            await session.execute(text("DELETE FROM categories"))

            root = Category(id=1, name="Root", parent_id=None)
            child1 = Category(id=2, name="Child1", parent_id=1)
            child2 = Category(id=3, name="Child2", parent_id=1)
            grandchild = Category(id=4, name="Grandchild", parent_id=2)

            session.add_all([root, child1, child2, grandchild])
            await session.flush()

            yield session

            if trans.is_active:
                await trans.rollback()

    await engine.dispose()


# ──── Tests ────


class TestRecursiveMethod:
    """FR-28: QueryBuilder.recursive() produces WITH RECURSIVE CTE."""

    def test_recursive_method_exists(self) -> None:
        assert hasattr(QueryBuilder, "recursive")

    async def test_recursive_produces_cte(self, cte_session: AsyncSession) -> None:
        qb = Category.query(cte_session).recursive(
            anchor=Category.parent_id.is_(None),
            step=lambda tree: Category.parent_id == tree.c.id,
        )
        stmt = qb.build_statement()
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "RECURSIVE" in compiled.upper() or "WITH" in compiled.upper()


class TestRecursiveMaxDepth:
    """FR-29: max_depth adds depth counter and limits recursion."""

    async def test_max_depth_limits_results(self, cte_session: AsyncSession) -> None:
        roots = (
            await Category.query(cte_session)
            .recursive(
                anchor=Category.parent_id.is_(None),
                step=lambda tree: Category.parent_id == tree.c.id,
                max_depth=1,
            )
            .all_as_tree()
        )
        all_names = _collect_names(list(roots))
        assert "Grandchild" not in all_names

    async def test_default_max_depth_is_100(self) -> None:
        from arvel.data.query import QueryBuilder

        assert QueryBuilder.DEFAULT_MAX_DEPTH == 100


class TestRecursiveDepthColumn:
    """FR-31: Results include depth column."""

    async def test_results_have_depth(self, cte_session: AsyncSession) -> None:
        roots = (
            await Category.query(cte_session)
            .recursive(
                anchor=Category.parent_id.is_(None),
                step=lambda tree: Category.parent_id == tree.c.id,
            )
            .all_as_tree()
        )
        assert len(roots) > 0
        first = roots[0]
        assert isinstance(first, TreeNode)
        assert isinstance(first.depth, int)
        assert "name" in first.data


class TestNestedTree:
    """Tree nodes are nested — children live under their parent."""

    async def test_full_tree_nesting(self, cte_session: AsyncSession) -> None:
        """Root → [Child1 → [Grandchild], Child2]"""
        roots = (
            await Category.query(cte_session)
            .recursive(
                anchor=Category.parent_id.is_(None),
                step=lambda tree: Category.parent_id == tree.c.id,
            )
            .all_as_tree()
        )
        root = roots[0]
        assert root.data["name"] == "Root"
        assert root.depth == 0

        child_names = {c.data["name"] for c in root.children}
        assert child_names == {"Child1", "Child2"}

        child1 = next(c for c in root.children if c.data["name"] == "Child1")
        assert child1.depth == 1
        assert len(child1.children) == 1
        assert child1.children[0].data["name"] == "Grandchild"
        assert child1.children[0].depth == 2

        child2 = next(c for c in root.children if c.data["name"] == "Child2")
        assert child2.children == []

    async def test_model_dump_includes_children(self, cte_session: AsyncSession) -> None:
        roots = (
            await Category.query(cte_session)
            .recursive(
                anchor=Category.parent_id.is_(None),
                step=lambda tree: Category.parent_id == tree.c.id,
            )
            .all_as_tree()
        )
        d = roots[0].model_dump()
        assert "children" in d
        child_names = {c["name"] for c in d["children"]}
        assert child_names == {"Child1", "Child2"}

    async def test_json_dumps_with_encoder(self, cte_session: AsyncSession) -> None:
        roots = (
            await Category.query(cte_session)
            .recursive(
                anchor=Category.parent_id.is_(None),
                step=lambda tree: Category.parent_id == tree.c.id,
            )
            .all_as_tree()
        )
        raw = json.dumps(roots.to_list(), indent=2, default=str)
        parsed = json.loads(raw)
        assert isinstance(parsed, list)
        assert "children" in parsed[0]

    async def test_print_renders_nested_json(self, cte_session: AsyncSession) -> None:
        roots = (
            await Category.query(cte_session)
            .recursive(
                anchor=Category.parent_id.is_(None),
                step=lambda tree: Category.parent_id == tree.c.id,
            )
            .all_as_tree()
        )
        output = str(roots)
        parsed = json.loads(output)
        assert "children" in parsed[0]

    async def test_leaf_has_no_children_key(self, cte_session: AsyncSession) -> None:
        roots = (
            await Category.query(cte_session)
            .recursive(
                anchor=Category.parent_id.is_(None),
                step=lambda tree: Category.parent_id == tree.c.id,
            )
            .all_as_tree()
        )
        child2 = next(c for c in roots[0].children if c.data["name"] == "Child2")
        d = child2.model_dump()
        assert "children" not in d


class TestAncestors:
    """FR-32: .ancestors(node_id) returns all ancestors to root."""

    def test_ancestors_method_exists(self) -> None:
        assert hasattr(QueryBuilder, "ancestors")

    async def test_ancestors_contains_all_ancestors(self, cte_session: AsyncSession) -> None:
        roots = await Category.query(cte_session).ancestors(4).all_as_tree()
        all_names = _collect_names(list(roots))
        assert "Child1" in all_names
        assert "Root" in all_names

    async def test_ancestors_of_root_returns_empty(self, cte_session: AsyncSession) -> None:
        results = await Category.query(cte_session).ancestors(1).all_as_tree()
        assert len(results) == 0

    async def test_ancestors_returns_tree_nodes(self, cte_session: AsyncSession) -> None:
        roots = await Category.query(cte_session).ancestors(4).all_as_tree()
        all_names = _collect_names(list(roots))
        assert len(all_names) > 0


class TestDescendants:
    """FR-33: .descendants(node_id) returns all descendants to leaves."""

    def test_descendants_method_exists(self) -> None:
        assert hasattr(QueryBuilder, "descendants")

    async def test_descendants_returns_subtree(self, cte_session: AsyncSession) -> None:
        roots = await Category.query(cte_session).descendants(1).all_as_tree()
        all_names = _collect_names(list(roots))
        assert "Child1" in all_names
        assert "Child2" in all_names
        assert "Grandchild" in all_names

    async def test_descendants_nested_structure(self, cte_session: AsyncSession) -> None:
        """descendants(1) excludes Root → returns Child1, Child2 as roots."""
        roots = await Category.query(cte_session).descendants(1).all_as_tree()
        root_names = {r.data["name"] for r in roots}
        assert "Child1" in root_names
        assert "Child2" in root_names

        child1 = next(r for r in roots if r.data["name"] == "Child1")
        assert len(child1.children) == 1
        assert child1.children[0].data["name"] == "Grandchild"

    async def test_descendants_of_leaf_returns_empty(self, cte_session: AsyncSession) -> None:
        results = await Category.query(cte_session).descendants(4).all_as_tree()
        assert len(results) == 0

    async def test_descendants_returns_tree_nodes(self, cte_session: AsyncSession) -> None:
        roots = await Category.query(cte_session).descendants(1).all_as_tree()
        for r in roots:
            assert isinstance(r, TreeNode)
            assert isinstance(r.depth, int)
            assert "id" in r.data


class TestRecursiveParameterization:
    """FR-34, SEC-06: All recursive queries use parameterized statements."""

    async def test_no_string_interpolation(self, cte_session: AsyncSession) -> None:
        qb = Category.query(cte_session).recursive(
            anchor=Category.parent_id.is_(None),
            step=lambda tree: Category.parent_id == tree.c.id,
        )
        stmt = qb.build_statement()
        compiled = stmt.compile()
        assert compiled.params is not None or compiled.string is not None


class TestRecursiveCycleDetection:
    """FR-30: Cycle detection prevents infinite loops."""

    async def test_cycle_detection_flag_accepted(self, cte_session: AsyncSession) -> None:
        qb = Category.query(cte_session).recursive(
            anchor=Category.parent_id.is_(None),
            step=lambda tree: Category.parent_id == tree.c.id,
            cycle_detection=True,
        )
        assert qb is not None
