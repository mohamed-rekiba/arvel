"""Recursive self-referential relations: descendants / ancestors + with_tree.

A node declares ``descendants`` / ``ancestors`` once as zero-arg accessors. The
same definition powers lazy ``.get()`` / ``.as_tree()`` and one-query eager
loading via ``with_tree(...)`` — Laravel's adjacency-list DX, batched.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Self

import pytest
from arvel.database import Model, TreeNode, foreign_id, id_, relationship, string
from arvel.database.exceptions import UnknownRelationError
from arvel.database.query_logging import QueryLog
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

if TYPE_CHECKING:
    from arvel.database.orm.relations import Ancestors, Descendants


class TreeCat(Model):
    __tablename__ = "tree_cats"
    __guarded__: ClassVar[list[str] | None] = []

    id: int = id_()
    name: str = string(80)
    parent_id: int | None = foreign_id("tree_cats.id", nullable=True)
    # Self-referential tree edge. with_tree("descendants") hydrates this in memory
    # so the loaded subtree is walkable via `node.children` with no extra query.
    children: list[TreeCat] = relationship(default_factory=list)

    def descendants(self) -> Descendants[Self]:
        return self.has_many_recursive(parent_key="parent_id")

    def ancestors(self) -> Ancestors[Self]:
        return self.belongs_to_recursive(parent_key="parent_id")


async def _setup(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


async def _seed() -> dict[str, TreeCat]:
    """
    root              root2
    ├── a             └── r2c
    │   └── gc
    │       └── ggc
    └── b
    """
    nodes: dict[str, TreeCat] = {}
    nodes["root"] = await TreeCat.create(name="root", parent_id=None)
    nodes["a"] = await TreeCat.create(name="a", parent_id=nodes["root"].id)
    nodes["b"] = await TreeCat.create(name="b", parent_id=nodes["root"].id)
    nodes["gc"] = await TreeCat.create(name="gc", parent_id=nodes["a"].id)
    nodes["ggc"] = await TreeCat.create(name="ggc", parent_id=nodes["gc"].id)
    nodes["root2"] = await TreeCat.create(name="root2", parent_id=None)
    nodes["r2c"] = await TreeCat.create(name="r2c", parent_id=nodes["root2"].id)
    return nodes


# ─── Registration ──────────────────────────────────────────────────────────────


class TestRegistration:
    def test_recursive_accessors_registered(self) -> None:
        assert TreeCat.__arvel_recursive_relations__ == frozenset({"descendants", "ancestors"})

    def test_builders_not_registered(self) -> None:
        """``has_many_recursive`` / ``belongs_to_recursive`` are builders, not accessors."""
        assert "has_many_recursive" not in TreeCat.__arvel_recursive_relations__
        assert "belongs_to_recursive" not in TreeCat.__arvel_recursive_relations__
        assert "has_many_recursive" not in TreeCat.__arvel_fk_relations__


# ─── Lazy read-back ──────────────────────────────────────────────────────────────


class TestLazy:
    async def test_descendants_flat(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        nodes = await _seed()

        kids = await nodes["root"].descendants().get()
        assert sorted(c.name for c in kids) == ["a", "b", "gc", "ggc"]

    async def test_descendants_leaf_is_empty(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        nodes = await _seed()

        assert list(await nodes["ggc"].descendants().get()) == []

    async def test_ancestors_flat(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        nodes = await _seed()

        anc = await nodes["ggc"].ancestors().get()
        assert sorted(c.name for c in anc) == ["a", "gc", "root"]

    async def test_max_depth_caps_walk(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        nodes = await _seed()

        kids = await nodes["root"].descendants().with_max_depth(1).get()
        assert sorted(c.name for c in kids) == ["a", "b"]

    async def test_chained_where_filters_walk(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        nodes = await _seed()

        # Excluding 'a' prunes its whole branch (gc, ggc).
        kids = await nodes["root"].descendants().where(TreeCat.name != "a").get()
        assert sorted(c.name for c in kids) == ["b"]


# ─── as_tree ─────────────────────────────────────────────────────────────────────


class TestAsTree:
    async def test_returns_tree_nodes(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        nodes = await _seed()

        tree = await nodes["root"].descendants().as_tree()
        assert all(isinstance(n, TreeNode) for n in tree)
        assert sorted(n.node.name for n in tree) == ["a", "b"]

    async def test_nesting_and_depth(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        nodes = await _seed()

        tree = await nodes["root"].descendants().as_tree()
        a_node = next(n for n in tree if n.node.name == "a")
        assert a_node.depth == 0
        gc_node = a_node.children[0]
        assert gc_node.node.name == "gc"
        assert gc_node.depth == 1
        assert gc_node.children[0].node.name == "ggc"
        assert gc_node.children[0].depth == 2

    async def test_single_round_trip(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        nodes = await _seed()

        with QueryLog.assert_max_queries(1):
            await nodes["root"].descendants().as_tree()


# ─── Eager with_tree ─────────────────────────────────────────────────────────────


class TestEagerWithTree:
    async def test_no_n_plus_one(self, engine: AsyncEngine, session: AsyncSession) -> None:
        """One query for the roots, one for the whole forest — read-back is free."""
        await _setup(engine)
        await _seed()

        with QueryLog.assert_max_queries(2):
            roots = (
                await TreeCat.where(TreeCat.__table__.c.parent_id.is_(None))
                .with_tree("descendants")
                .get()
            )
            by_name = {r.name: sorted(c.name for c in await r.descendants().get()) for r in roots}

        assert by_name == {"root": ["a", "b", "gc", "ggc"], "root2": ["r2c"]}

    async def test_as_tree_from_cache(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        await _seed()

        roots = (
            await TreeCat.where(TreeCat.__table__.c.parent_id.is_(None))
            .with_tree("descendants")
            .get()
        )
        root = next(r for r in roots if r.name == "root")
        with QueryLog.assert_max_queries(0):
            tree = await root.descendants().as_tree()
        a_node = next(n for n in tree if n.node.name == "a")
        assert a_node.children[0].node.name == "gc"

    async def test_constraint_filters_walk(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        await _seed()

        roots = await (
            TreeCat.where(TreeCat.__table__.c.parent_id.is_(None))
            .with_tree("descendants", constraint=lambda q: q.where(TreeCat.name != "gc"))
            .get()
        )
        root = next(r for r in roots if r.name == "root")
        kids = await root.descendants().get()
        # Pruning 'gc' also drops its child 'ggc'.
        assert sorted(c.name for c in kids) == ["a", "b"]

    async def test_max_depth(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        await _seed()

        roots = await (
            TreeCat.where(TreeCat.__table__.c.parent_id.is_(None))
            .with_tree("descendants", max_depth=2)
            .get()
        )
        root = next(r for r in roots if r.name == "root")
        kids = await root.descendants().get()
        assert sorted(c.name for c in kids) == ["a", "b", "gc"]

    async def test_eager_ancestors(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        await _seed()

        with QueryLog.assert_max_queries(2):
            leaves = await TreeCat.where(TreeCat.name == "ggc").with_tree("ancestors").get()
            chain = {leaves[0].name: sorted(a.name for a in await leaves[0].ancestors().get())}

        assert chain == {"ggc": ["a", "gc", "root"]}

    async def test_plain_with_routes_to_recursive(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        """A recursive relation passed to with_() loads with defaults too."""
        await _setup(engine)
        await _seed()

        roots = (
            await TreeCat.where(TreeCat.__table__.c.parent_id.is_(None)).with_("descendants").get()
        )
        root = next(r for r in roots if r.name == "root")
        with QueryLog.assert_max_queries(0):
            kids = await root.descendants().get()
        assert sorted(c.name for c in kids) == ["a", "b", "gc", "ggc"]


# ─── Sync tree navigation (node.children) ────────────────────────────────────────


class TestChildrenGraph:
    async def test_walk_children_no_queries(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        """After with_tree, walk the whole subtree via node.children — sync, query-free."""
        await _setup(engine)
        await _seed()

        roots = (
            await TreeCat.where(TreeCat.__table__.c.parent_id.is_(None))
            .with_tree("descendants")
            .get()
        )
        root = next(r for r in roots if r.name == "root")

        with QueryLog.assert_max_queries(0):
            assert sorted(c.name for c in root.children) == ["a", "b"]
            a = next(c for c in root.children if c.name == "a")
            assert [c.name for c in a.children] == ["gc"]
            gc = a.children[0]
            assert [c.name for c in gc.children] == ["ggc"]
            # Leaf nodes surface as an empty collection, not a lazy load.
            assert gc.children[0].children == []

    async def test_second_root_isolated(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        await _seed()

        roots = (
            await TreeCat.where(TreeCat.__table__.c.parent_id.is_(None))
            .with_tree("descendants")
            .get()
        )
        root2 = next(r for r in roots if r.name == "root2")
        with QueryLog.assert_max_queries(0):
            assert [c.name for c in root2.children] == ["r2c"]
            assert root2.children[0].children == []

    async def test_max_depth_caps_children(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        await _seed()

        roots = await (
            TreeCat.where(TreeCat.__table__.c.parent_id.is_(None))
            .with_tree("descendants", max_depth=1)
            .get()
        )
        root = next(r for r in roots if r.name == "root")
        with QueryLog.assert_max_queries(0):
            assert sorted(c.name for c in root.children) == ["a", "b"]
            # Depth 1 stops here: 'a' has children in the DB but none were loaded.
            a = next(c for c in root.children if c.name == "a")
            assert a.children == []

    async def test_constraint_prunes_children(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        await _seed()

        roots = await (
            TreeCat.where(TreeCat.__table__.c.parent_id.is_(None))
            .with_tree("descendants", constraint=lambda q: q.where(TreeCat.name != "a"))
            .get()
        )
        root = next(r for r in roots if r.name == "root")
        with QueryLog.assert_max_queries(0):
            # Pruning 'a' drops its whole branch; only 'b' remains under root.
            assert [c.name for c in root.children] == ["b"]


# ─── Errors / unsupported ────────────────────────────────────────────────────────


class TestErrors:
    def test_with_tree_rejects_non_recursive(self) -> None:
        with pytest.raises(UnknownRelationError):
            TreeCat.with_tree("name")

    async def test_where_has_recursive_is_clear_error(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        with pytest.raises(TypeError, match="recursive relation"):
            await TreeCat.where_has("descendants").get()
