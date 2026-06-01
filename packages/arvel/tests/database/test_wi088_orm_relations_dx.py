"""Method-style FK relations: eager loading + N+1 elimination (Laravel DX).

Relations are defined once as zero-arg accessor methods returning ``HasMany`` /
``HasOne`` / ``BelongsTo``. The same definition powers lazy queries, eager
loading (``with_("items")``), cached read-back (``await owner.items.get``),
and ``where_has`` / ``with_count`` — no separate descriptor declaration."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from arvel.database import Model, foreign_id, id_, string
from arvel.database.query_logging import QueryLog
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

if TYPE_CHECKING:
    from arvel.database.orm.relations import BelongsTo, HasMany, HasOne


class RelOwner(Model):
    __tablename__ = "rel_owners"
    __guarded__: ClassVar[list[str] | None] = []

    id: int = id_()
    name: str = string(80)

    def items(self) -> HasMany[RelItem]:
        return self.has_many(RelItem, foreign_key="owner_id")

    def latest_item(self) -> HasOne[RelItem]:
        return self.has_one(RelItem, foreign_key="owner_id")


class RelItem(Model):
    __tablename__ = "rel_items"
    __guarded__: ClassVar[list[str] | None] = []

    id: int = id_()
    label: str = string(80)
    owner_id: int | None = foreign_id("rel_owners.id", nullable=True)

    def owner(self) -> BelongsTo[RelOwner]:
        return self.belongs_to(RelOwner, foreign_key="owner_id")


async def _setup(engine: AsyncEngine) -> None:
    from arvel.database.model import Model as BaseModel

    async with engine.begin() as conn:
        await conn.run_sync(BaseModel.metadata.create_all)


async def _seed() -> tuple[RelOwner, RelOwner]:
    o1 = await RelOwner.create(name="o1")
    o2 = await RelOwner.create(name="o2")
    await RelItem.create(label="a", owner_id=o1.id)
    await RelItem.create(label="b", owner_id=o1.id)
    await RelItem.create(label="c", owner_id=o2.id)
    return o1, o2


# ─── Registration ─────────────────────────────────────────────────────────────


class TestRegistration:
    def test_accessors_are_registered(self) -> None:
        """The metaclass records zero-arg relation accessors for the eager engine."""
        assert "items" in RelOwner.__arvel_fk_relations__
        assert "latest_item" in RelOwner.__arvel_fk_relations__
        assert "owner" in RelItem.__arvel_fk_relations__

    def test_builder_helpers_not_registered(self) -> None:
        """``has_many`` and friends take arguments — they're not accessors."""
        assert "has_many" not in RelOwner.__arvel_fk_relations__
        assert "belongs_to" not in RelItem.__arvel_fk_relations__


# ─── Eager loading (has_many) ──────────────────────────────────────────────────


class TestEagerHasMany:
    async def test_no_n_plus_one(self, engine: AsyncEngine, session: AsyncSession) -> None:
        """with_("items") + cached read-back stays at two queries for any owner count."""
        await _setup(engine)
        await _seed()

        with QueryLog.assert_max_queries(2):
            owners = await RelOwner.with_("items").all()
            counts = {o.name: len(await o.items().get()) for o in owners}

        assert counts == {"o1": 2, "o2": 1}

    async def test_lazy_path_still_queries(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        """Without with_, the accessor falls through to a real query."""
        await _setup(engine)
        o1, _ = await _seed()

        fresh = await RelOwner.find(o1.id)
        assert fresh is not None
        items = await fresh.items().get()
        assert len(items) == 2


# ─── Eager loading (has_one / belongs_to) ──────────────────────────────────────


class TestEagerHasOneBelongsTo:
    async def test_has_one_cached_readback(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        await _seed()

        owners = await RelOwner.with_("latest_item").all()
        with QueryLog.assert_max_queries(0):
            for owner in owners:
                assert await owner.latest_item().first() is not None

    async def test_belongs_to_cached_readback(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        await _seed()

        items = await RelItem.with_("owner").all()
        with QueryLog.assert_max_queries(0):
            owners = [await it.owner().first() for it in items]
        assert all(o is not None for o in owners)
        assert {o.name for o in owners if o is not None} == {"o1", "o2"}


# ─── Chaperone (inverse hydration over method relations) ───────────────────────


class TestChaperone:
    async def test_inverse_inferred_no_extra_query(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        """chaperone hydrates each child's belongs_to back to the loaded owner."""
        await _setup(engine)
        await _seed()

        owners = await RelOwner.with_({"items": lambda q: q.chaperone()}).all()
        target = next(o for o in owners if o.name == "o1")

        with QueryLog.assert_max_queries(0):
            items = await target.items().get()
            for item in items:
                assert await item.owner().first() is target

    async def test_explicit_inverse_name(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        await _seed()

        owners = await RelOwner.with_({"items": lambda q: q.chaperone("owner")}).all()
        target = next(o for o in owners if o.name == "o1")

        with QueryLog.assert_max_queries(0):
            for item in await target.items().get():
                assert await item.owner().first() is target


# ─── where_has / with_count over method relations ──────────────────────────────


class TestRelationConstraints:
    async def test_where_has(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        await RelOwner.create(name="childless")
        await _seed()

        with_items = await RelOwner.where_has("items").get()
        assert {o.name for o in with_items} == {"o1", "o2"}

    async def test_where_has_with_constraint(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        await _seed()

        matched = await RelOwner.where_has("items", lambda q: q.where(RelItem.label == "c")).get()
        assert {o.name for o in matched} == {"o2"}

    async def test_with_count(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        await _seed()

        owners = await RelOwner.with_count("items").get()
        by_name = {o.name: o.items_count for o in owners}
        assert by_name == {"o1": 2, "o2": 1}


# ─── Lazy batch load onto fetched instances ────────────────────────────────────


class TestLoadAfterFetch:
    async def test_collection_load(self, engine: AsyncEngine, session: AsyncSession) -> None:
        """ModelCollection.load batches a method-style relation into the cache."""
        await _setup(engine)
        await _seed()

        owners = await RelOwner.all()
        await owners.load("items")
        with QueryLog.assert_max_queries(0):
            counts = {o.name: len(await o.items().get()) for o in owners}
        assert counts == {"o1": 2, "o2": 1}

    async def test_model_load(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        o1, _ = await _seed()

        fresh = await RelOwner.find(o1.id)
        assert fresh is not None
        await fresh.load("items")
        with QueryLog.assert_max_queries(0):
            assert len(await fresh.items().get()) == 2


# ─── QueryLog.assert_max_queries ───────────────────────────────────────────────


class TestAssertMaxQueries:
    async def test_passes_within_limit(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        await RelOwner.create(name="q1")
        with QueryLog.assert_max_queries(5) as log:
            await RelOwner.all()
        assert len(log.queries) <= 5

    async def test_fails_when_exceeded(self, engine: AsyncEngine, session: AsyncSession) -> None:
        import pytest

        await _setup(engine)
        await RelOwner.create(name="o0")
        with pytest.raises(AssertionError, match="queries"), QueryLog.assert_max_queries(0):
            await RelOwner.all()

    def test_is_context_manager_factory(self) -> None:
        cm = QueryLog.assert_max_queries(10)
        assert hasattr(cm, "__enter__") or hasattr(cm, "__aenter__")
