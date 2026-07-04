"""09 DB-QUERY B3 — EloquentCollection: Builder.get()/relation get() return a model-aware
Collection (load/load_missing/model_keys/find/contains/fresh/make_hidden/make_visible/
to_dict/to_json/only/except_/to_query), while staying list-compatible (Sequence conformance)."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model
from arvel.database.collection import EloquentCollection


class Author(Model):
    __table_name__ = "ec_authors"
    __fields__ = {"name": str}
    __fillable__ = ["name"]

    def articles(self) -> object:
        return self.has_many(Article)


class Article(Model):
    __table_name__ = "ec_articles"
    __fields__ = {"title": str, "author_id": int}
    __fillable__ = ["title", "author_id"]


async def _setup() -> ConnectionResolver:
    db = ConnectionResolver()
    for model in (Author, Article):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    return db


async def test_all_and_get_return_an_eloquent_collection() -> None:
    db = await _setup()
    try:
        await Author.create(name="ada")
        await Author.create(name="bob")
        result = await Author.all()
        assert isinstance(result, EloquentCollection)
        assert isinstance(result, Sequence)
        assert isinstance(result, list) is False  # divergence: a Collection, not a bare list
        assert len(result) == 2
        assert result[0].name == "ada"
        assert [a.name for a in result] == ["ada", "bob"]  # plain iteration still works
    finally:
        await db.dispose()


async def test_model_keys_and_find_and_contains() -> None:
    db = await _setup()
    try:
        ada = await Author.create(name="ada")
        bob = await Author.create(name="bob")
        authors = await Author.all()

        assert authors.model_keys() == [ada.id, bob.id]
        assert authors.find(bob.id) is not None and authors.find(bob.id).name == "bob"
        assert authors.find(999) is None
        assert authors.contains(bob.id) is True
        assert authors.contains(bob) is True
        assert authors.contains(999) is False
    finally:
        await db.dispose()


async def test_only_and_except_filter_by_primary_key() -> None:
    db = await _setup()
    try:
        a = await Author.create(name="a")
        await Author.create(name="b")
        c = await Author.create(name="c")
        authors = await Author.all()

        assert [m.name for m in authors.only([a.id, c.id])] == ["a", "c"]
        assert [m.name for m in authors.except_([a.id, c.id])] == ["b"]
    finally:
        await db.dispose()


async def test_to_dict_and_to_json() -> None:
    db = await _setup()
    try:
        await Author.create(name="ada")
        authors = await Author.all()
        assert authors.to_dict() == [m.to_dict() for m in authors]
        assert authors.to_dict()[0]["name"] == "ada"
        assert '"name": "ada"' in authors.to_json()
    finally:
        await db.dispose()


async def test_make_hidden_and_make_visible_fan_to_members() -> None:
    db = await _setup()
    try:
        await Author.create(name="ada")
        await Author.create(name="bob")
        authors = await Author.all()
        authors.make_hidden("name")
        assert all("name" not in m.to_dict() for m in authors)
        authors.make_visible("name")
        assert all("name" in m.to_dict() for m in authors)
    finally:
        await db.dispose()


async def test_load_and_load_missing_batch_eager_load() -> None:
    db = await _setup()
    try:
        ada = await Author.create(name="ada")
        bob = await Author.create(name="bob")
        await Article.create(title="hi", author_id=ada.id)
        await Article.create(title="yo", author_id=bob.id)

        authors = await Author.all()
        assert all("articles" not in a._relations for a in authors)

        await authors.load("articles")
        assert {a._relations["articles"][0].title for a in authors if a._relations["articles"]} == {
            "hi",
            "yo",
        }

        # load_missing is a no-op the second time (already loaded on every member)
        await authors.load_missing("articles")
        assert isinstance(authors[0]._relations["articles"], EloquentCollection)
    finally:
        await db.dispose()


async def test_fresh_reloads_every_member_in_one_batched_query() -> None:
    db = await _setup()
    try:
        await Author.create(name="ada")
        await Author.create(name="bob")
        authors = await Author.all()

        await Author.where(name="ada").update({"name": "ada2"})
        refreshed = await authors.fresh()
        assert sorted(m.name for m in refreshed) == ["ada2", "bob"]
    finally:
        await db.dispose()


async def test_to_query_round_trips() -> None:
    db = await _setup()
    try:
        ada = await Author.create(name="ada")
        await Author.create(name="bob")
        authors = await Author.all()

        only_ada = authors.only([ada.id])
        requeried = await only_ada.to_query().get()
        assert [m.name for m in requeried] == ["ada"]
    finally:
        await db.dispose()


async def test_relation_get_returns_eloquent_collection() -> None:
    db = await _setup()
    try:
        ada = await Author.create(name="ada")
        await Article.create(title="hi", author_id=ada.id)
        articles = await ada.articles().get()
        assert isinstance(articles, EloquentCollection)

        empty = await (await Author.create(name="bob")).articles().get()
        assert isinstance(empty, EloquentCollection)
        assert empty == []
    finally:
        await db.dispose()
