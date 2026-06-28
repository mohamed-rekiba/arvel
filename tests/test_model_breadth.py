"""C3b — Model breadth: mass-assignment, timestamps, finders, change-tracking, enum."""

from __future__ import annotations

import enum

import pytest
import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model
from arvel.database.model import ModelNotFound


class Status(enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"


class Article(Model):
    __fields__ = {"title": str, "status": str, "views": int}
    __fillable__ = ["title", "status"]  # 'views' is guarded
    __casts__ = {"status": Status}
    __hidden__ = ["views"]
    __timestamps__ = True


async def _setup() -> ConnectionResolver:
    db = ConnectionResolver()
    Article.set_connection(db)
    await db.execute(sa.schema.CreateTable(Article.__table__))
    return db


def test_timestamp_columns_added() -> None:
    assert {"created_at", "updated_at"} <= set(Article.__table__.c.keys())


async def test_mass_assignment_guards_non_fillable() -> None:
    db = await _setup()
    try:
        article = await Article.create(title="t", status="draft", views=999)
        assert article.title == "t"
        assert "views" not in article._attributes
    finally:
        await db.dispose()


async def test_timestamps_set_on_create() -> None:
    db = await _setup()
    try:
        article = await Article.create(title="t", status="draft")
        assert article.created_at is not None
        assert article.updated_at is not None
    finally:
        await db.dispose()


async def test_enum_cast_roundtrip() -> None:
    db = await _setup()
    try:
        await Article.create(title="t", status=Status.PUBLISHED)
        found = await Article.find(1)
        assert found is not None
        assert found.status is Status.PUBLISHED  # cast on read
    finally:
        await db.dispose()


async def test_find_or_fail() -> None:
    db = await _setup()
    try:
        await Article.create(title="t", status="draft")
        assert (await Article.find_or_fail(1)).title == "t"
        with pytest.raises(ModelNotFound):
            await Article.find_or_fail(999)
    finally:
        await db.dispose()


async def test_first_or_create_and_update_or_create() -> None:
    db = await _setup()
    try:
        a1 = await Article.first_or_create({"title": "unique"}, {"status": "draft"})
        a2 = await Article.first_or_create({"title": "unique"}, {"status": "published"})
        assert a1.id == a2.id  # second call found the existing row
        assert await Article.where(title="unique").count() == 1

        await Article.update_or_create({"title": "unique"}, {"status": "published"})
        refreshed = await Article.find(a1.id)
        assert refreshed is not None
        assert refreshed.status is Status.PUBLISHED
    finally:
        await db.dispose()


async def test_change_tracking() -> None:
    db = await _setup()
    try:
        await Article.create(title="orig", status="draft")
        article = await Article.find(1)
        assert article is not None
        assert article.is_dirty() is False
        article.title = "changed"
        assert article.was_changed("title") is True
        assert article.get_original("title") == "orig"
        await article.save()
        assert article.is_clean() is True
        fresh = await article.fresh()
        assert fresh is not None
        assert fresh.title == "changed"
    finally:
        await db.dispose()


async def test_make_hidden_and_visible() -> None:
    db = await _setup()
    try:
        article = await Article.create(title="t", status="draft")
        assert "title" in article.to_dict()
        article.make_hidden("title")
        assert "title" not in article.to_dict()
        article.make_visible("title")
        assert "title" in article.to_dict()
    finally:
        await db.dispose()


async def test_increment() -> None:
    db = await _setup()
    try:
        article = await Article.create(title="t", status="draft")
        await article.increment("views", 5)
        reloaded = await Article.find(article.id)
        assert reloaded is not None
        assert reloaded.views == 5
    finally:
        await db.dispose()
