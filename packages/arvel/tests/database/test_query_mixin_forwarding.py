"""Model class-level shortcuts forward to QueryBuilder.

QueryMixin exposes the whole QueryBuilder surface as classmethods so
``Model.where_null(...)`` works without ``Model.query`` first. These are thin
delegators; this suite exercises the ones that are otherwise only reached via
the builder instance."""

from __future__ import annotations

from arvel.database import (
    Model,
    QueryBuilder,
    SoftDeletes,
    Timestamps,
    field,
    id_,
    integer,
    relationship,
    string,
)
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


class QmfRecord(Model, Timestamps, SoftDeletes):
    __tablename__ = "qmf_records"
    id: int = id_()
    name: str = string(80)
    votes: int = integer(default=0)
    children: list[QmfChild] = relationship("QmfChild", back_populates="parent", init=False)


class QmfChild(Model):
    __tablename__ = "qmf_children"
    id: int = id_()
    votes: int = integer(default=0)
    parent_id: int | None = field(foreign_key="qmf_records.id", default=None)
    parent: QmfRecord | None = relationship("QmfRecord", back_populates="children", init=False)


async def _setup(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


class TestBuildOnlyForwarding:
    """Each shortcut builds a QueryBuilder without hitting the database."""

    def test_or_where_value_family(self) -> None:
        assert isinstance(QmfRecord.or_where_in(QmfRecord.id, [1, 2]), QueryBuilder)
        assert isinstance(QmfRecord.or_where_not_in(QmfRecord.id, [1, 2]), QueryBuilder)
        assert isinstance(QmfRecord.or_where_between(QmfRecord.votes, 1, 5), QueryBuilder)
        assert isinstance(QmfRecord.or_where_null(QmfRecord.name), QueryBuilder)
        assert isinstance(QmfRecord.or_where_not_null(QmfRecord.name), QueryBuilder)
        assert isinstance(QmfRecord.or_where_raw("1 = 1"), QueryBuilder)

    def test_or_where_date_family(self) -> None:
        assert isinstance(QmfRecord.or_where_date("created_at", "2020-01-01"), QueryBuilder)
        assert isinstance(QmfRecord.or_where_time("created_at", "12:00:00"), QueryBuilder)
        assert isinstance(QmfRecord.or_where_year("created_at", 2020), QueryBuilder)
        assert isinstance(QmfRecord.or_where_month("created_at", 1), QueryBuilder)
        assert isinstance(QmfRecord.or_where_day("created_at", 1), QueryBuilder)

    def test_or_where_like_and_set_family(self) -> None:
        assert isinstance(QmfRecord.or_where_like("name", "%a%"), QueryBuilder)
        assert isinstance(QmfRecord.or_where_not_like("name", "%a%"), QueryBuilder)
        assert isinstance(QmfRecord.or_where_all(["name"], "=", "x"), QueryBuilder)
        assert isinstance(QmfRecord.or_where_none(["name"], "=", "x"), QueryBuilder)
        assert isinstance(QmfRecord.or_where_any(["name"], "=", "x"), QueryBuilder)

    def test_json_and_exists(self) -> None:
        assert isinstance(QmfRecord.where_json_contains("name", "x"), QueryBuilder)
        assert isinstance(QmfRecord.where_json_path("name", "$.a", 1), QueryBuilder)
        assert isinstance(
            QmfRecord.where_exists(lambda q: q.where(QmfRecord.id == 1)), QueryBuilder
        )

    def test_ordering_grouping_having(self) -> None:
        assert isinstance(QmfRecord.reorder(QmfRecord.id), QueryBuilder)
        assert isinstance(QmfRecord.offset(5), QueryBuilder)
        assert isinstance(QmfRecord.group_by_raw("name"), QueryBuilder)
        assert isinstance(QmfRecord.having("votes", ">", 0), QueryBuilder)
        assert isinstance(QmfRecord.having_null("votes"), QueryBuilder)
        assert isinstance(QmfRecord.having_between("votes", 1, 5), QueryBuilder)
        assert isinstance(QmfRecord.having_raw("votes > 0"), QueryBuilder)

    def test_with_aggregates_and_conditionals(self) -> None:
        assert isinstance(QmfRecord.with_avg("children", "votes"), QueryBuilder)
        assert isinstance(QmfRecord.with_min("children", "votes"), QueryBuilder)
        assert isinstance(QmfRecord.with_exists("children"), QueryBuilder)
        assert isinstance(QmfRecord.unless(False, lambda q: q), QueryBuilder)
        assert isinstance(QmfRecord.tap(lambda _q: None), QueryBuilder)

    def test_debug_helpers(self) -> None:
        assert isinstance(QmfRecord.to_raw_sql(), str)
        assert isinstance(QmfRecord.get_bindings(), list)


class TestTerminalForwarding:
    """Read/write shortcuts that round-trip through the session."""

    async def test_read_terminals(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        await QmfRecord.create(name="a", votes=1)
        await QmfRecord.create(name="b", votes=2)

        assert len(await QmfRecord.all()) == 2
        assert len(await QmfRecord.get()) == 2
        assert (await QmfRecord.first_or_fail()).name in {"a", "b"}
        assert (await QmfRecord.first_or(lambda: QmfRecord(name="z"))).name in {"a", "b"}
        assert await QmfRecord.doesnt_exist() is False

    async def test_pagination_shortcuts(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        await QmfRecord.create(name="a", votes=1)

        assert (await QmfRecord.paginate(10)).total == 1
        assert len((await QmfRecord.simple_paginate(10)).items) == 1
        assert len((await QmfRecord.cursor_paginate(10)).items) == 1

    async def test_iteration_shortcuts(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        await QmfRecord.create(name="a", votes=1)

        seen: list[int] = []

        async def collect(rows: list[QmfRecord]) -> None:
            seen.extend(r.votes for r in rows)

        await QmfRecord.chunk(10, collect)
        await QmfRecord.each(lambda _r: _noop())
        # Generators: calling the shortcut runs the delegation; no iteration needed.
        assert QmfRecord.lazy_by_id() is not None
        assert QmfRecord.stream() is not None
        assert seen == [1]

    async def test_write_shortcuts(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        a = await QmfRecord.create(name="a", votes=1)

        assert await QmfRecord.update({"votes": 5}) >= 1
        await QmfRecord.update_or_create({"name": "a"}, {"votes": 7})
        assert await QmfRecord.increment("votes", 1) >= 1
        assert await QmfRecord.decrement("votes", 1) >= 1
        assert await QmfRecord.increment_each({"votes": 1}) >= 1
        assert await QmfRecord.decrement_each({"votes": 1}) >= 1
        # Empty force_destroy is a no-op that returns 0.
        assert await QmfRecord.force_destroy() == 0
        assert await QmfRecord.force_destroy(a.id) >= 1


async def _noop() -> None:
    return None
