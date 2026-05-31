"""Database engine — SQL ILIKE search hydrated through the ORM."""

from __future__ import annotations

from arvel.database import Model
from arvel_search import Search, SearchManager
from arvel_search.dtos import SearchQuery
from arvel_search.engines import DatabaseEngine
from arvel_search.exceptions import SearchError
from sqlalchemy.ext.asyncio import AsyncSession
from search_support import Article, make_config


async def _bind_database() -> SearchManager:
    manager = SearchManager(make_config(driver="database"))
    Search.bind(manager)
    return manager


class TestDatabaseEngine:
    async def test_ilike_matches_declared_columns(
        self, tables: None, session: AsyncSession
    ) -> None:
        await _bind_database()
        a1 = await Article.create(title="Python guide", body="x")
        await Article.create(title="Rust guide", body="y")

        results = await Article.search("python").get()
        assert [r.id for r in results] == [a1.id]

    async def test_case_insensitive(self, tables: None, session: AsyncSession) -> None:
        await _bind_database()
        await Article.create(title="PYTHON", body="x")
        keys = await Article.search("python").keys()
        assert len(keys) == 1

    async def test_count_without_hydration(self, tables: None, session: AsyncSession) -> None:
        await _bind_database()
        await Article.create(title="Python a", body="x")
        await Article.create(title="Python b", body="x")
        assert await Article.search("python").count() == 2

    async def test_where_filter(self, tables: None, session: AsyncSession) -> None:
        await _bind_database()
        await Article.create(title="Python", body="x", category="news")
        await Article.create(title="Python", body="x", category="blog")
        keys = await Article.search("python").where("category", "news").keys()
        assert len(keys) == 1

    async def test_writes_are_noops(self) -> None:
        engine = DatabaseEngine()
        await engine.upsert_documents("idx", [{"id": "1"}], key="id")
        await engine.remove_documents("idx", ["1"])
        await engine.flush("idx")

    async def test_search_without_model_raises(self) -> None:
        engine = DatabaseEngine()
        try:
            await engine.search(SearchQuery(index="idx", query="x"))
        except SearchError:
            return
        raise AssertionError("expected SearchError when no model bound")


class TestNoTableLeak:
    def test_category_not_indexed(self) -> None:
        # Defense in depth: the DB engine only scans __searchable__ columns.
        _ = Model  # keep import meaningful
        assert "category" not in Article.searchable_columns()
