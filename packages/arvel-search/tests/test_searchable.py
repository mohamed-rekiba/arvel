"""Searchable mixin — index naming, payload shaping, and auto-sync."""

from __future__ import annotations

import warnings

import pytest
from arvel.database import Model, id_, string
from arvel_search import Search, SearchManager
from arvel_search.dtos import SearchQuery
from arvel_search.searchable import Searchable
from sqlalchemy.ext.asyncio import AsyncSession
from search_support import Article, make_config


class TestMixinDefaults:
    def test_index_name_defaults_to_tablename(self) -> None:
        assert Article.search_index_name() == "search_articles"

    def test_explicit_index_name_wins(self) -> None:
        class Custom(Model, Searchable):
            __tablename__ = "customs"
            __search_index__ = "custom_index"
            id: int = id_()
            name: str = string(50)

        assert Custom.search_index_name() == "custom_index"

    def test_searchable_array_only_includes_declared_columns(self) -> None:
        article = Article(title="Hi", body="there", category="secret-cat")
        array = article.to_searchable_array()

        assert set(array) == {"id", "title", "body"}
        assert "category" not in array  # not declared → never indexed

    def test_searchable_columns_reflects_declaration(self) -> None:
        assert Article.searchable_columns() == ("title", "body")


class TestSensitiveFieldWarning:
    def test_warns_when_sensitive_column_declared_searchable(self) -> None:
        with pytest.warns(UserWarning, match="sensitive field"):

            class Leaky(Model, Searchable):
                __tablename__ = "leaky"
                __searchable__ = ("title", "password")
                id: int = id_()
                title: str = string(50)
                password: str = string(50)

        assert Leaky.search_index_name() == "leaky"

    def test_no_warning_for_clean_columns(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("error")

            class Clean(Model, Searchable):
                __tablename__ = "clean"
                __searchable__ = ("title",)
                id: int = id_()
                title: str = string(50)

        assert Clean.searchable_columns() == ("title",)


class TestAutoSync:
    async def test_create_indexes_document(
        self, tables: None, session: AsyncSession, collection_engine: SearchManager
    ) -> None:
        article = await Article.create(title="Python tips", body="indexing works")

        result = await collection_engine.engine().search(_query("python"))
        assert result.ids == [str(article.id)]

    async def test_update_reindexes_document(
        self, tables: None, session: AsyncSession, collection_engine: SearchManager
    ) -> None:
        article = await Article.create(title="Draft", body="placeholder")
        article.title = "Published headline"
        await article.save()

        hit = await collection_engine.engine().search(_query("published"))
        assert hit.ids == [str(article.id)]
        stale = await collection_engine.engine().search(_query("draft"))
        assert stale.ids == []

    async def test_delete_removes_document(
        self, tables: None, session: AsyncSession, collection_engine: SearchManager
    ) -> None:
        article = await Article.create(title="Ephemeral", body="soon gone")
        await article.delete()

        result = await collection_engine.engine().search(_query("ephemeral"))
        assert result.ids == []

    async def test_sync_disabled_skips_indexing(self, tables: None, session: AsyncSession) -> None:
        manager = SearchManager(make_config(driver="collection", sync_on_save=False))
        Search.bind(manager)

        article = await Article.create(title="Quiet", body="no auto index")
        result = await manager.engine().search(_query("quiet"))
        assert result.ids == []

        # Manual indexing still works.
        await article.searchable()
        result = await manager.engine().search(_query("quiet"))
        assert result.ids == [str(article.id)]

    async def test_no_engine_bound_is_a_noop(self, tables: None, session: AsyncSession) -> None:
        # No Search.manager bound → the auto-sync hook must no-op, not raise.
        article = await Article.create(title="Orphan", body="no backend")
        assert article.id is not None


def _query(term: str) -> SearchQuery:
    return SearchQuery(index="search_articles", query=term)
