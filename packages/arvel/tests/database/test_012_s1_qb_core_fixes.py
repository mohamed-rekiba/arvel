"""QueryBuilder core fixes and write-side operations."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from arvel.database import Model, QueryBuilder, boolean, id_, integer, string
from arvel.database.columns import datetime as datetime_col
from arvel.database.scope import scope
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

# ─── Test models ─────────────────────────────────────────────────────────────


class ItemS1(Model):
    __tablename__ = "items_s1"
    id: int = id_()
    name: str = string(80)
    score: int = integer(default=0)
    active: bool = boolean(default=True)


class PostS1(Model):
    __tablename__ = "posts_s1"
    id: int = id_()
    title: str = string(200)
    deleted_at: datetime | None = datetime_col(nullable=True, init=False, default=None)

    @scope
    @staticmethod
    def titled(
        qb: QueryBuilder[PostS1],
        prefix: str,
    ) -> QueryBuilder[PostS1]:
        return qb.where(PostS1.title.startswith(prefix))


async def _setup(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


# ───  Model class-level QB forwarding ──────────────────────────────


async def test_model_classmethod_where_returns_qb(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    """User.where(...) forwards to User.where(...) via _ModelMeta."""
    await _setup(engine)
    result = ItemS1.where(ItemS1.active == True)  # noqa: E712
    assert isinstance(result, QueryBuilder)


async def test_model_classmethod_order_by_returns_qb(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    await _setup(engine)
    result = ItemS1.order_by(ItemS1.name)
    assert isinstance(result, QueryBuilder)


async def test_model_classmethod_where_executes(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    await ItemS1.create(name="alpha", score=10)
    await ItemS1.create(name="beta", score=5)
    rows = await ItemS1.where(ItemS1.name == "alpha").all()
    assert len(rows) == 1
    assert rows[0].name == "alpha"


async def test_model_find_still_uses_explicit_classmethod(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    """Explicit classmethods must not be overridden by __getattr__."""
    await _setup(engine)
    item = await ItemS1.create(name="found", score=1)
    fetched = await ItemS1.find(item.id)
    assert fetched is not None
    assert fetched.name == "found"


async def test_model_query_still_works(engine: AsyncEngine, session: AsyncSession) -> None:
    """Model.query continues to work unchanged."""
    await _setup(engine)
    qb = ItemS1.query()
    assert isinstance(qb, QueryBuilder)


async def test_model_private_attr_raises(engine: AsyncEngine, session: AsyncSession) -> None:
    """Private attribute names must raise AttributeError, not forward to QB."""
    with pytest.raises(AttributeError):
        _ = ItemS1.__nonexistent_private__  # intentional: verifies the guard raises AttributeError


# ───  Soft-delete QB filter ────────────────────────────────────────


async def test_soft_delete_default_excludes_deleted(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    """Model.all must exclude soft-deleted rows when SoftDeletes is mixed in."""
    from arvel.database.model import SoftDeletes

    class UserSD(Model, SoftDeletes):
        __tablename__ = "users_sd"
        id: int = id_()
        name: str = string(80)

    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)

    await UserSD.create(name="alive")
    deleted = await UserSD.create(name="dead")
    deleted.deleted_at = datetime.now(UTC)
    await deleted.save()

    rows = await UserSD.all()
    assert all(r.name != "dead" for r in rows)
    assert any(r.name == "alive" for r in rows)


async def test_soft_delete_with_trashed_includes_all(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    """with_trashed includes soft-deleted rows."""
    from arvel.database.model import SoftDeletes

    class UserWT(Model, SoftDeletes):
        __tablename__ = "users_wt"
        id: int = id_()
        name: str = string(80)

    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)

    await UserWT.create(name="alive")
    deleted = await UserWT.create(name="dead")
    deleted.deleted_at = datetime.now(UTC)
    await deleted.save()

    rows = await UserWT.with_trashed().all()
    names = {r.name for r in rows}
    assert "alive" in names
    assert "dead" in names


async def test_soft_delete_only_trashed(engine: AsyncEngine, session: AsyncSession) -> None:
    """only_trashed returns only soft-deleted rows."""
    from arvel.database.model import SoftDeletes

    class UserOT(Model, SoftDeletes):
        __tablename__ = "users_ot"
        id: int = id_()
        name: str = string(80)

    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)

    await UserOT.create(name="alive")
    deleted = await UserOT.create(name="dead")
    deleted.deleted_at = datetime.now(UTC)
    await deleted.save()

    rows = await UserOT.only_trashed().all()
    assert all(r.name == "dead" for r in rows)
    assert len(rows) == 1


async def test_model_without_soft_deletes_unaffected(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    """Model without SoftDeletes must not have with_trashed / only_trashed."""
    await _setup(engine)
    with pytest.raises(AttributeError):
        ItemS1.with_trashed()


# ───  Local scopes callable via QB ─────────────────────────────────


async def test_local_scope_callable_no_args(engine: AsyncEngine, session: AsyncSession) -> None:
    """@scope decorated methods must be callable on QB instances."""
    await _setup(engine)
    await PostS1.create(title="Hello world")
    await PostS1.create(title="Other post")
    rows = await PostS1.titled("Hello").all()
    assert len(rows) == 1
    assert rows[0].title == "Hello world"


async def test_local_scope_via_classmethod_shortcut(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    """PostS1.titled('H') must work as a class-level call (via _ModelMeta)."""
    await _setup(engine)
    await PostS1.create(title="Hi there")
    rows = await PostS1.titled("Hi").all()
    assert len(rows) == 1


async def test_undefined_method_raises_attribute_error(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    """Unknown method not decorated with @scope must raise AttributeError."""
    await _setup(engine)
    missing = "no_such_scope"
    with pytest.raises(AttributeError):
        getattr(PostS1, missing)()


# ───  QB write operations ──────────────────────────────────────────


async def test_qb_insert_bulk(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    await ItemS1.insert(
        [
            {"name": "x", "score": 1},
            {"name": "y", "score": 2},
        ]
    )
    assert await ItemS1.count() == 2


async def test_qb_insert_get_id_returns_pk(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    pk = await ItemS1.insert_get_id({"name": "solo", "score": 5})
    assert isinstance(pk, int)
    assert pk >= 1


async def test_qb_update_returns_rowcount(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    await ItemS1.create(name="upd", score=0)
    await ItemS1.create(name="upd", score=0)
    n = await ItemS1.where(ItemS1.name == "upd").update({"score": 99})
    assert n == 2
    rows = await ItemS1.where(ItemS1.name == "upd").all()
    assert all(r.score == 99 for r in rows)


async def test_qb_update_or_insert_creates_when_missing(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    await _setup(engine)
    await ItemS1.update_or_insert(
        where={"name": "uoi"},
        values={"score": 7},
    )
    assert await ItemS1.where(ItemS1.name == "uoi").count() == 1


async def test_qb_update_or_insert_updates_when_existing(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    await _setup(engine)
    await ItemS1.create(name="uoi2", score=1)
    await ItemS1.update_or_insert(
        where={"name": "uoi2"},
        values={"score": 42},
    )
    rows = await ItemS1.where(ItemS1.name == "uoi2").all()
    assert len(rows) == 1
    assert rows[0].score == 42


async def test_qb_upsert(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    await ItemS1.upsert(
        [{"name": "upsert_me", "score": 1}],
        unique_by=["name"],
        update=["score"],
    )
    await ItemS1.upsert(
        [{"name": "upsert_me", "score": 99}],
        unique_by=["name"],
        update=["score"],
    )
    rows = await ItemS1.where(ItemS1.name == "upsert_me").all()
    assert len(rows) == 1
    assert rows[0].score == 99


async def test_qb_increment(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    item = await ItemS1.create(name="incr", score=5)
    await ItemS1.where(ItemS1.id == item.id).increment("score", 3)
    await session.refresh(item)
    assert item.score == 8


async def test_qb_decrement(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    item = await ItemS1.create(name="decr", score=10)
    await ItemS1.where(ItemS1.id == item.id).decrement("score", 4)
    await session.refresh(item)
    assert item.score == 6


async def test_qb_delete_returns_rowcount(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    await ItemS1.create(name="del1", score=0)
    await ItemS1.create(name="del1", score=0)
    n = await ItemS1.where(ItemS1.name == "del1").delete()
    assert n == 2
    assert await ItemS1.count() == 0


async def test_qb_write_without_session_or_config_raises(engine: AsyncEngine) -> None:
    """A write with no active session and no configured default reports the missing config."""
    from arvel.database.db import DB

    previous = type.__getattribute__(DB, "_session_maker")
    type.__setattr__(DB, "_session_maker", None)
    try:
        with pytest.raises(RuntimeError, match="DB not configured"):
            await ItemS1.insert([{"name": "fail", "score": 0}])
    finally:
        type.__setattr__(DB, "_session_maker", previous)


async def test_qb_write_autocommits_on_default_connection(engine: AsyncEngine) -> None:
    """No bound session: the write opens its own session and commits (Laravel parity)."""
    from arvel.database.db import DB
    from sqlalchemy.ext.asyncio import async_sessionmaker

    await _setup(engine)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    previous = type.__getattribute__(DB, "_session_maker")
    try:
        DB.configure(maker)
        await ItemS1.insert([{"name": "committed", "score": 7}])
        # A fresh session sees the committed row — proof the write didn't just flush.
        async with maker() as verify:
            count = await verify.scalar(
                text("SELECT COUNT(*) FROM items_s1 WHERE name = :n"), {"n": "committed"}
            )
        assert count == 1
    finally:
        type.__setattr__(DB, "_session_maker", previous)


# ───  Extra aggregates ─────────────────────────────────────────────


async def test_sum(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    for i in [10, 20, 30]:
        await ItemS1.create(name="s", score=i)
    total = await ItemS1.where(ItemS1.name == "s").sum("score")
    assert total == 60


async def test_avg(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    for i in [10, 20, 30]:
        await ItemS1.create(name="a", score=i)
    result = await ItemS1.where(ItemS1.name == "a").avg("score")
    assert isinstance(result, float)
    assert abs(result - 20.0) < 1e-9


async def test_max(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    for i in [3, 7, 2]:
        await ItemS1.create(name="m", score=i)
    result = await ItemS1.where(ItemS1.name == "m").max("score")
    assert result == 7


async def test_min(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    for i in [3, 7, 2]:
        await ItemS1.create(name="mn", score=i)
    result = await ItemS1.where(ItemS1.name == "mn").min("score")
    assert result == 2


async def test_aggregates_return_none_on_empty(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    # sum follows Laravel: 0 for an empty set, not null.
    assert await ItemS1.where(ItemS1.name == "nope").sum("score") == 0
    assert await ItemS1.where(ItemS1.name == "nope").avg("score") is None
    assert await ItemS1.where(ItemS1.name == "nope").max("score") is None
    assert await ItemS1.where(ItemS1.name == "nope").min("score") is None
