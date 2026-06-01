"""SearchFake — assertion helpers over an in-memory engine."""

from __future__ import annotations

import pytest
from arvel.database import Model, id_, string
from arvel_search import Search
from arvel_search.searchable import Searchable
from search_support import Article
from sqlalchemy.ext.asyncio import AsyncSession


class FakeDoc(Model, Searchable):
    __tablename__ = "fake_docs"
    __searchable__ = ("title",)
    id: int = id_()
    title: str = string(50)


class TestSearchFake:
    async def test_assert_indexed_passes_after_save(
        self, tables: None, session: AsyncSession
    ) -> None:
        fake = Search.fake()
        article = await Article.create(title="Hello", body="world")
        fake.assert_indexed(article)

    async def test_assert_nothing_indexed_on_empty(self) -> None:
        fake = Search.fake()
        fake.assert_nothing_indexed()

    async def test_assert_nothing_indexed_fails_after_save(
        self, tables: None, session: AsyncSession
    ) -> None:
        fake = Search.fake()
        await Article.create(title="X", body="y")
        with pytest.raises(AssertionError):
            fake.assert_nothing_indexed()

    async def test_assert_removed_after_delete(self, tables: None, session: AsyncSession) -> None:
        fake = Search.fake()
        article = await Article.create(title="Temp", body="z")
        await article.delete()
        fake.assert_removed(article)

    async def test_assert_indexed_count(self, tables: None, session: AsyncSession) -> None:
        fake = Search.fake()
        await Article.create(title="A", body="x")
        await Article.create(title="B", body="x")
        fake.assert_indexed_count(2)

    async def test_assert_not_indexed_for_unsaved(self) -> None:
        fake = Search.fake()
        doc = FakeDoc(title="never-saved")
        fake.assert_not_indexed(doc)

    async def test_fake_is_searchable_in_memory(self, tables: None, session: AsyncSession) -> None:
        Search.fake()
        await Article.create(title="Searchable Python", body="body")
        results = await Article.search("python").keys()
        assert len(results) == 1
