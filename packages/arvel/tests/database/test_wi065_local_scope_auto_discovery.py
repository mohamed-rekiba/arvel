"""``scope_<name>`` auto-discovery.

Local query scopes via the Laravel-style naming convention: define
``scope_active(self, query)`` on a model and call ``Post.active`` or
``Post.query.active`` — no decorator required.

The framework discovers ``scope_*`` methods at lookup time on both the
class itself (``_ModelMeta.__getattr__``) and the live query builder
(``QueryBuilder.__getattr__``). Methods receive the model class as
``self`` (Python equivalent of Laravel's "fresh model instance" pattern)
followed by the query and the user's positional/keyword args, and must
return the modified query."""

from __future__ import annotations

from typing import Any

import pytest
from arvel.database import Model, QueryBuilder, id_, string
from sqlalchemy.ext.asyncio import AsyncSession


class _Post(Model):
    __tablename__ = "posts_wi065"
    id: int = id_()
    title: str = string(80)
    status: str = string(20, default="draft")
    category: str = string(20, default="general")

    def scope_active(self, query: QueryBuilder[_Post]) -> QueryBuilder[_Post]:
        return query.where(_Post.__table__.c.status == "active")

    def scope_published(self, query: QueryBuilder[_Post]) -> QueryBuilder[_Post]:
        return query.where(_Post.__table__.c.status != "draft")

    def scope_in_category(
        self,
        query: QueryBuilder[_Post],
        category: str,
    ) -> QueryBuilder[_Post]:
        return query.where(_Post.__table__.c.category == category)


async def _setup(engine: Any) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


# ---------------------------------------------------------------------------
# Class-level entry: `Post.active` creates a fresh QB
# ---------------------------------------------------------------------------


class TestClassLevelScopeEntry:
    async def test_class_level_call_returns_query_builder(
        self, engine: Any, session: AsyncSession
    ) -> None:
        await _setup(engine)
        qb = _Post.active()
        assert isinstance(qb, QueryBuilder)

    async def test_class_level_scope_filters_results(
        self, engine: Any, session: AsyncSession
    ) -> None:
        await _setup(engine)
        await _Post.create(title="A", status="active")
        await _Post.create(title="B", status="draft")
        rows = await _Post.active().all()
        assert [r.title for r in rows] == ["A"]

    async def test_scope_accepts_positional_args(self, engine: Any, session: AsyncSession) -> None:
        await _setup(engine)
        await _Post.create(title="A", status="active", category="news")
        await _Post.create(title="B", status="active", category="blog")
        rows = await _Post.in_category("news").all()
        assert [r.title for r in rows] == ["A"]

    async def test_unknown_attribute_still_raises(self, engine: Any, session: AsyncSession) -> None:
        await _setup(engine)
        with pytest.raises(AttributeError):
            _Post.this_scope_does_not_exist()


# ---------------------------------------------------------------------------
# QB-level chain: qb.active.published.get
# ---------------------------------------------------------------------------


class TestQueryBuilderScopeChain:
    async def test_two_scopes_chain(self, engine: Any, session: AsyncSession) -> None:
        await _setup(engine)
        await _Post.create(title="A", status="active")
        await _Post.create(title="B", status="draft")
        await _Post.create(title="C", status="active")
        rows = await _Post.active().published().all()
        assert sorted(r.title for r in rows) == ["A", "C"]

    async def test_qb_entry_then_scope(self, engine: Any, session: AsyncSession) -> None:
        await _setup(engine)
        await _Post.create(title="A", status="active")
        await _Post.create(title="B", status="draft")
        rows = await _Post.active().all()
        assert [r.title for r in rows] == ["A"]

    async def test_unknown_scope_on_qb_raises(self, engine: Any, session: AsyncSession) -> None:
        await _setup(engine)
        qb = _Post.query()
        with pytest.raises(AttributeError):
            qb.nonexistent_scope()


# ---------------------------------------------------------------------------
# Discovery rules
# ---------------------------------------------------------------------------


class TestDiscoveryRules:
    async def test_prefix_must_be_scope_(self, engine: Any, session: AsyncSession) -> None:
        """A method named ``active`` (no ``scope_`` prefix) is NOT a scope."""

        class _OtherPost(Model):
            __tablename__ = "posts_wi065_other"
            id: int = id_()
            status: str = string(20, default="draft")

            def active(self, query: QueryBuilder[_OtherPost]) -> QueryBuilder[_OtherPost]:
                return query.where(_OtherPost.__table__.c.status == "active")

        await _setup(engine)
        # Class-level: no discovery, instance method shadows nothing usable here
        # because we look for scope_<name>, not bare <name>.
        with pytest.raises(AttributeError):
            _OtherPost.published_only()

    async def test_scope_name_strips_prefix(self, engine: Any, session: AsyncSession) -> None:
        await _setup(engine)
        await _Post.create(title="A", status="active")
        rows = await _Post.active().all()
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# Self argument shape
# ---------------------------------------------------------------------------


class TestScopeSelfShape:
    async def test_self_is_a_post_instance(self, engine: Any, session: AsyncSession) -> None:
        """``self`` inside the scope method is callable with ``isinstance``
        against the model class, even though it carries no DB state."""

        captured: list[Any] = []

        class _Tagged(Model):
            __tablename__ = "posts_wi065_tagged"
            id: int = id_()
            status: str = string(20, default="x")

            def scope_anything(self, query: QueryBuilder[_Tagged]) -> QueryBuilder[_Tagged]:
                captured.append(self)
                return query

        await _setup(engine)
        _Tagged.anything()
        assert len(captured) == 1
        assert isinstance(captured[0], _Tagged)
