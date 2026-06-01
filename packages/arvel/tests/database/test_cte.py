"""CTE, recursive queries, and TreeNode assembly."""

from __future__ import annotations

from typing import Any

from arvel.database import Model, foreign_id, id_, string
from arvel.database.tree import TreeNode
from sqlalchemy.ext.asyncio import AsyncSession


class Category(Model):
    __tablename__ = "cte_categories"
    id: int = id_()
    name: str = string(80)
    parent_id: int | None = foreign_id("cte_categories.id", nullable=True)


async def _create_tables(engine: Any) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


# ─── TreeNode dataclass ───────────────────────────────────────────────────────


def test_tree_node_is_generic() -> None:
    """TreeNode[T] is a generic dataclass."""
    node = TreeNode(node="leaf", depth=1, children=[])
    assert node.node == "leaf"
    assert node.depth == 1
    assert node.children == []


def test_tree_node_nested() -> None:
    child = TreeNode(node="child", depth=1, children=[])
    root = TreeNode(node="root", depth=0, children=[child])
    assert len(root.children) == 1
    assert root.children[0].node == "child"


# ─── with_cte ────────────────────────────────────────────────────────────────


async def test_with_cte_attaches_cte(engine: Any, session: AsyncSession) -> None:
    """with_cte attaches CTE; SQL contains WITH clause."""
    await _create_tables(engine)
    from sqlalchemy import select

    roots_cte = select(Category).where(Category.__table__.c.parent_id.is_(None)).cte("roots")
    sql = Category.with_cte("roots", roots_cte).to_sql()
    assert "WITH" in sql.upper()
    assert "roots" in sql


async def test_with_cte_multiple_chains(engine: Any, session: AsyncSession) -> None:
    """Multiple CTEs can be chained."""
    await _create_tables(engine)
    from sqlalchemy import select

    cte_a = select(Category).where(Category.__table__.c.parent_id.is_(None)).cte("cte_a")
    cte_b = select(Category).where(Category.__table__.c.name == "x").cte("cte_b")
    sql = Category.with_cte("cte_a", cte_a).with_cte("cte_b", cte_b).to_sql()
    assert "cte_a" in sql
    assert "cte_b" in sql


# ─── recursive ───────────────────────────────────────────────────────────────


async def test_recursive_returns_recursive_query_builder(
    engine: Any, session: AsyncSession
) -> None:
    """recursive returns RecursiveQueryBuilder."""
    await _create_tables(engine)
    from arvel.database.query import RecursiveQueryBuilder

    builder = Category.where(Category.__table__.c.parent_id.is_(None)).recursive("parent_id")
    assert isinstance(builder, RecursiveQueryBuilder)


async def test_recursive_sql_contains_with_recursive(engine: Any, session: AsyncSession) -> None:
    """Rendered SQL includes WITH RECURSIVE clause."""
    await _create_tables(engine)
    sql = Category.where(Category.__table__.c.parent_id.is_(None)).recursive("parent_id").to_sql()
    upper = sql.upper()
    assert "WITH" in upper
    assert "RECURSIVE" in upper


async def test_recursive_depth_col_in_sql(engine: Any, session: AsyncSession) -> None:
    """depth_col adds a computed column to the recursive CTE."""
    await _create_tables(engine)
    sql = (
        Category.query()
        .where(Category.__table__.c.parent_id.is_(None))
        .recursive("parent_id", depth_col="depth")
        .to_sql()
    )
    assert "depth" in sql.lower()


# ─── as_tree ─────────────────────────────────────────────────────────────────


async def _build_tree(engine: Any, session: AsyncSession) -> None:
    """Build a tree:
    root (id=1)
    ├── child_a (id=2, parent=1)
    │   └── grandchild (id=4, parent=2)
    └── child_b (id=3, parent=1)"""
    await _create_tables(engine)
    root = await Category.create(name="root", parent_id=None)
    child_a = await Category.create(name="child_a", parent_id=root.id)
    _child_b = await Category.create(name="child_b", parent_id=root.id)
    _grand = await Category.create(name="grandchild", parent_id=child_a.id)


async def test_as_tree_returns_list_of_tree_nodes(engine: Any, session: AsyncSession) -> None:
    """as_tree returns list[TreeNode[Category]]."""
    await _build_tree(engine, session)
    trees = await (
        Category.query()
        .where(Category.__table__.c.parent_id.is_(None))
        .recursive("parent_id", depth_col="depth")
        .as_tree()
    )
    assert isinstance(trees, list)
    assert len(trees) == 1
    root_node = trees[0]
    assert isinstance(root_node, TreeNode)
    assert root_node.node.name == "root"
    assert root_node.depth == 0


async def test_as_tree_assembles_children(engine: Any, session: AsyncSession) -> None:
    """Children are nested under their parent TreeNode."""
    await _build_tree(engine, session)
    trees = await (
        Category.query()
        .where(Category.__table__.c.parent_id.is_(None))
        .recursive("parent_id", depth_col="depth")
        .as_tree()
    )
    root = trees[0]
    assert len(root.children) == 2
    child_names = {c.node.name for c in root.children}
    assert child_names == {"child_a", "child_b"}


async def test_as_tree_nested_grandchildren(engine: Any, session: AsyncSession) -> None:
    """Grandchildren are nested under the correct child."""
    await _build_tree(engine, session)
    trees = await (
        Category.query()
        .where(Category.__table__.c.parent_id.is_(None))
        .recursive("parent_id", depth_col="depth")
        .as_tree()
    )
    root = trees[0]
    child_a = next(n for n in root.children if n.node.name == "child_a")
    assert len(child_a.children) == 1
    assert child_a.children[0].node.name == "grandchild"


async def test_as_tree_single_round_trip(engine: Any, session: AsyncSession) -> None:
    """as_tree is a single DB round-trip (verified by query count fixture)."""
    await _build_tree(engine, session)
    query_count = 0

    from sqlalchemy import event

    def _count_queries(
        conn: Any,
        cursor: Any,
        statement: Any,
        parameters: Any,
        context: Any,
        executemany: Any,
    ) -> None:
        nonlocal query_count
        query_count += 1

    event.listen(engine.sync_engine, "after_cursor_execute", _count_queries)
    try:
        await (
            Category.query()
            .where(Category.__table__.c.parent_id.is_(None))
            .recursive("parent_id", depth_col="depth")
            .as_tree()
        )
        assert query_count == 1
    finally:
        event.remove(engine.sync_engine, "after_cursor_execute", _count_queries)
