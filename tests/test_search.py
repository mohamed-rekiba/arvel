"""arvel.search — Scout-style search module: ArrayEngine, SearchManager driver resolution, and
the Searchable mixin (auto-sync on save/delete + Model.search hydration)."""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model
from arvel.kernel.application import Application
from arvel.search import ArrayEngine, Searchable, SearchManager
from arvel.support.manager import MissingExtraError


class Article(Searchable, Model):  # Searchable BEFORE Model so its _fire override wins (MRO)
    __fields__ = {"title": str, "body": str}
    __fillable__ = ["title", "body"]


# --- ArrayEngine -----------------------------------------------------------
async def test_array_engine_index_search_delete() -> None:
    engine = ArrayEngine()
    await engine.index("articles", 1, {"title": "async python", "body": "fast web"})
    await engine.index("articles", 2, {"title": "ruby on rails", "body": "slow"})
    assert len(await engine.search("articles", "python")) == 1
    assert len(await engine.search("articles", "SLOW")) == 1  # case-insensitive
    await engine.delete("articles", 1)
    assert await engine.search("articles", "python") == []


# --- SearchManager ---------------------------------------------------------
def test_manager_default_is_array() -> None:
    assert isinstance(SearchManager().driver(), ArrayEngine)


def test_manager_unknown_driver_raises_missing_extra() -> None:
    with pytest.raises(MissingExtraError):
        SearchManager().driver("algolia")  # no such driver / extra installed


# --- Searchable mixin (auto-sync + search) ---------------------------------
async def _app_with_search() -> tuple[Application, ConnectionResolver]:
    app = Application.configure().with_config({"search": {"driver": "array"}}).create()
    app.singleton("search", lambda a: SearchManager(a))
    db = ConnectionResolver()
    Article.set_connection(db)
    await db.execute(sa.schema.CreateTable(Article.__table__))
    return app, db


async def test_save_indexes_and_search_hydrates_models() -> None:
    _app, db = await _app_with_search()
    try:
        await Article.create(title="async python", body="fast web")
        await Article.create(title="ruby on rails", body="slow")
        hits = await Article.search("python")
        assert [h.title for h in hits] == ["async python"]
        assert isinstance(hits[0], Article)  # hydrated model
    finally:
        await db.dispose()


async def test_delete_removes_from_index() -> None:
    _app, db = await _app_with_search()
    try:
        article = await Article.create(title="async python", body="fast web")
        assert len(await Article.search("python")) == 1
        await article.delete()
        assert await Article.search("python") == []
    finally:
        await db.dispose()


async def test_searchable_metadata_defaults() -> None:
    assert Article.searchable_as() == "articles"
    article = Article(title="x", body="y")
    article.id = 7
    assert article.get_search_key() == 7
    assert article.to_searchable_array()["title"] == "x"
