"""SearchBuilder — chaining, terminals, hydration order, and error path."""

from __future__ import annotations

import pytest
from arvel.database import Model, id_, string
from arvel_search import Search, SearchEngineNotConfigured, SearchManager
from arvel_search.builder import SearchBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from support import Article


async def _seed(count: int) -> list[Article]:
    return [
        await Article.create(title=f"Python part {i}", body=f"chapter {i}", category="series")
        for i in range(count)
    ]


class TestTerminals:
    async def test_get_hydrates_models(
        self, tables: None, session: AsyncSession, collection_engine: SearchManager
    ) -> None:
        await _seed(3)
        results = await Article.search("python").get()
        assert len(results) == 3
        assert all(isinstance(r, Article) for r in results)

    async def test_keys_returns_ids_without_hydration(
        self, tables: None, session: AsyncSession, collection_engine: SearchManager
    ) -> None:
        articles = await _seed(2)
        keys = await Article.search("python").keys()
        assert set(keys) == {str(a.id) for a in articles}

    async def test_count_returns_total(
        self, tables: None, session: AsyncSession, collection_engine: SearchManager
    ) -> None:
        await _seed(4)
        assert await Article.search("python").count() == 4

    async def test_limit_and_offset(
        self, tables: None, session: AsyncSession, collection_engine: SearchManager
    ) -> None:
        await _seed(5)
        page = await Article.search("python").limit(2).offset(1).get()
        assert len(page) == 2

    async def test_first_returns_single(
        self, tables: None, session: AsyncSession, collection_engine: SearchManager
    ) -> None:
        await _seed(2)
        first = await Article.search("python").first()
        assert isinstance(first, Article)

    async def test_first_returns_none_on_no_match(
        self, tables: None, session: AsyncSession, collection_engine: SearchManager
    ) -> None:
        await _seed(1)
        assert await Article.search("nonexistent-term").first() is None


class TestFilters:
    async def test_where_filters_on_indexed_field(
        self, tables: None, session: AsyncSession, collection_engine: SearchManager
    ) -> None:
        # body is in __searchable__, so the collection engine can filter on it.
        await Article.create(title="Go guide", body="alpha")
        await Article.create(title="Go cookbook", body="beta")

        keys = await Article.search("go").where("body", "alpha").keys()
        assert len(keys) == 1


class TestPagination:
    async def test_paginate_metadata(
        self, tables: None, session: AsyncSession, collection_engine: SearchManager
    ) -> None:
        await _seed(7)
        page = await Article.search("python").paginate(per_page=3, page=2)

        assert page.total == 7
        assert page.per_page == 3
        assert page.current_page == 2
        assert page.last_page == 3
        assert page.has_more is True
        assert len(page.items) == 3


class TestHydrationOrder:
    async def test_get_order_matches_engine_keys(
        self, tables: None, session: AsyncSession, collection_engine: SearchManager
    ) -> None:
        await _seed(4)
        engine = collection_engine.engine()

        builder: SearchBuilder[Article] = SearchBuilder(Article, "python", engine=engine)
        expected = (await builder.raw()).ids
        rows = await SearchBuilder(Article, "python", engine=engine).get()
        assert [str(r.id) for r in rows] == expected


class TestErrorPath:
    async def test_search_without_engine_raises_descriptive_error(
        self, tables: None, session: AsyncSession
    ) -> None:
        Search.manager = None
        with pytest.raises(SearchEngineNotConfigured, match="No search engine"):
            await Article.search("python").keys()


class TestUnrelatedModel:
    def test_plain_model_has_no_search(self) -> None:
        class Plain(Model):
            __tablename__ = "plain_things"
            id: int = id_()
            name: str = string(50)

        assert not hasattr(Plain, "search")
