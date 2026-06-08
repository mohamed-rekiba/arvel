"""Streaming terminals must never silently drop eager loads.

A server-side cursor (``stream()``) holds one batch in memory and cannot satisfy
ANY eager load, so requesting one fails fast with ``EagerLoadNotStreamableError``
instead of issuing per-row N+1 queries or leaving relations empty (Laravel's
"cursor can't eager-load; use lazy" contract, made explicit/fail-fast). This
covers every registration bucket: SA ``selectinload`` (``_eager_loads``),
pivot/morph/FK-method (``_async_eager``), recursive (``_tree_eager``), and
chaperone (``_chaperones``).

``RecursiveQueryBuilder.as_tree()`` materializes the whole forest in memory, so
it honors eager loads exactly like its sibling ``all()`` — no silent drop.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Self

import pytest
from arvel.database import Model, TreeNode, foreign_id, id_, relationship, string
from arvel.database.exceptions import EagerLoadNotStreamableError
from arvel.database.orm._eager import get_eager_relation
from arvel.database.query_logging import QueryLog
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

if TYPE_CHECKING:
    from arvel.database.orm.relations import Descendants, HasMany


class SgOwner(Model):
    __tablename__ = "sg_owners"
    __guarded__: ClassVar[list[str] | None] = []

    id: int = id_()
    name: str = string(80)
    posts: list[SgPost] = relationship(
        "SgPost", back_populates="owner", init=False, default_factory=list
    )

    def items(self) -> HasMany[SgItem]:
        return self.has_many(SgItem, foreign_key="owner_id")


class SgItem(Model):
    __tablename__ = "sg_items"
    __guarded__: ClassVar[list[str] | None] = []

    id: int = id_()
    label: str = string(80)
    owner_id: int | None = foreign_id("sg_owners.id", nullable=True)


class SgPost(Model):
    __tablename__ = "sg_posts"
    __guarded__: ClassVar[list[str] | None] = []

    id: int = id_()
    title: str = string(80)
    owner_id: int | None = foreign_id("sg_owners.id", nullable=True)
    owner: SgOwner | None = relationship("SgOwner", back_populates="posts", init=False)


class SgNode(Model):
    __tablename__ = "sg_nodes"
    __guarded__: ClassVar[list[str] | None] = []

    id: int = id_()
    name: str = string(80)
    parent_id: int | None = foreign_id("sg_nodes.id", nullable=True)
    children: list[SgNode] = relationship(default_factory=list)

    def descendants(self) -> Descendants[Self]:
        return self.has_many_recursive(parent_key="parent_id")

    def tags(self) -> HasMany[SgTag]:
        return self.has_many(SgTag, foreign_key="node_id")


class SgTag(Model):
    __tablename__ = "sg_tags"
    __guarded__: ClassVar[list[str] | None] = []

    id: int = id_()
    label: str = string(80)
    node_id: int | None = foreign_id("sg_nodes.id", nullable=True)


async def _setup(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


def _assert_remediation_hints(exc: EagerLoadNotStreamableError) -> None:
    message = str(exc)
    assert "lazy" in message and "chunk" in message


# ─── SPEC-1/SPEC-2: stream() fails fast on EVERY eager-load bucket ────────────


async def test_stream_rejects_fk_method_eager_load(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    # _async_eager bucket (also the path for pivot/morph relations).
    await _setup(engine)
    o1 = await SgOwner.create(name="o1")
    await SgItem.create(label="a", owner_id=o1.id)

    with pytest.raises(EagerLoadNotStreamableError) as exc:
        async for _ in SgOwner.with_("items").order_by("id").stream():
            pass

    assert exc.value.relations == ["items"]
    assert "items" in str(exc.value)
    _assert_remediation_hints(exc.value)


async def test_stream_rejects_selectin_relationship(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    # _eager_loads bucket: SA relationship() / selectinload. selectinload does not
    # load reliably under a server-side cursor — it would leave `owner.posts`
    # empty — so it must be rejected too, not silently dropped (SPEC-2).
    await _setup(engine)
    o1 = await SgOwner.create(name="o1")
    await SgPost.create(title="p1", owner_id=o1.id)

    with pytest.raises(EagerLoadNotStreamableError) as exc:
        async for _ in SgOwner.with_("posts").order_by("id").stream():
            pass

    assert exc.value.relations == ["posts"]
    _assert_remediation_hints(exc.value)


async def test_stream_rejects_tree_eager_load(engine: AsyncEngine, session: AsyncSession) -> None:
    # _tree_eager bucket: recursive eager load registered via with_tree().
    await _setup(engine)
    await SgNode.create(name="root", parent_id=None)

    with pytest.raises(EagerLoadNotStreamableError) as exc:
        async for _ in SgNode.query().with_tree("descendants").stream():
            pass

    assert exc.value.relations == ["descendants"]
    _assert_remediation_hints(exc.value)


async def test_stream_rejects_chaperone_eager_load(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    # _chaperones bucket: a with_() closure that requests inverse hydration.
    await _setup(engine)
    o1 = await SgOwner.create(name="o1")
    await SgPost.create(title="p1", owner_id=o1.id)

    with pytest.raises(EagerLoadNotStreamableError) as exc:
        async for _ in SgOwner.with_({"posts": lambda q: q.chaperone()}).stream():
            pass

    # The closure registers both the eager load and a chaperone; both are reported.
    assert "posts" in exc.value.relations
    _assert_remediation_hints(exc.value)


# ─── SPEC-3: stream() still works with no eager loads ─────────────────────────


async def test_stream_without_eager_loads_yields_all_rows(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    await _setup(engine)
    for i in range(1, 6):
        await SgOwner.create(name=f"o{i}")

    ids = [o.id async for o in SgOwner.query().order_by("id").stream(batch_size=2)]
    assert ids == [1, 2, 3, 4, 5]


# ─── SPEC-4: as_tree() honors eager loads (mirrors all()) ─────────────────────


def _flatten(forest: list[TreeNode[SgNode]]) -> list[TreeNode[SgNode]]:
    flat: list[TreeNode[SgNode]] = []
    stack = list(forest)
    while stack:
        node = stack.pop()
        flat.append(node)
        stack.extend(node.children)
    return flat


def _cached_tag_labels(row: SgNode) -> list[str]:
    cached = get_eager_relation(row, "tags")
    assert cached is not None  # eager-cached, not lazy-loaded
    labels: list[str] = []
    for tag in cached:
        assert isinstance(tag, SgTag)
        labels.append(tag.label)
    return labels


async def test_as_tree_honors_eager_load_like_all(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    await _setup(engine)
    root = await SgNode.create(name="root", parent_id=None)
    a = await SgNode.create(name="a", parent_id=root.id)
    await SgTag.create(label="t-root", node_id=root.id)
    await SgTag.create(label="t-a", node_id=a.id)

    # as_tree() must run the same eager pipeline as all(): one CTE query for the
    # forest + one batched IN(...) for tags. Before the fix, as_tree() skipped
    # eager loading and silently dropped with_("tags").
    with QueryLog.assert_max_queries(2):
        forest = await SgNode.recursive(parent_key="parent_id").with_("tags").as_tree()
        for node in _flatten(forest):
            await node.node.tags().get()  # served from cache, no query

    by_name = {node.node.name: node.node for node in _flatten(forest)}
    assert _cached_tag_labels(by_name["root"]) == ["t-root"]
    assert _cached_tag_labels(by_name["a"]) == ["t-a"]


async def test_as_tree_eager_state_matches_all(engine: AsyncEngine, session: AsyncSession) -> None:
    """as_tree() and all() must leave identical per-node eager-cache state."""
    await _setup(engine)
    root = await SgNode.create(name="root", parent_id=None)
    a = await SgNode.create(name="a", parent_id=root.id)
    await SgTag.create(label="t-root", node_id=root.id)
    await SgTag.create(label="t-a", node_id=a.id)

    flat_rows = await SgNode.recursive(parent_key="parent_id").with_("tags").all()
    all_state = {row.name: _cached_tag_labels(row) for row in flat_rows}

    forest = await SgNode.recursive(parent_key="parent_id").with_("tags").as_tree()
    tree_state = {node.node.name: _cached_tag_labels(node.node) for node in _flatten(forest)}

    assert tree_state == all_state
    assert all_state == {"root": ["t-root"], "a": ["t-a"]}
