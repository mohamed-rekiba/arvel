"""T5.3 — Active-Record Model: table build, CRUD, casts, dirty, to_dict, queries."""

from __future__ import annotations

import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model


class Post(Model):
    __fields__ = {"title": str, "views": int, "published": bool, "meta": dict}
    __fillable__ = ["title", "views", "published", "meta"]
    __casts__ = {"published": "bool", "meta": "json"}
    __hidden__ = ["views"]


async def _setup() -> ConnectionResolver:
    db = ConnectionResolver()
    Post.set_connection(db)
    await db.execute(sa.schema.CreateTable(Post.__table__))
    return db


def test_metaclass_builds_core_table() -> None:
    assert Post.__table__ is not None
    assert Post.__table__.name == "posts"  # pluralized snake-case class name
    assert "id" in Post.__table__.c  # auto primary key
    assert {"title", "views", "published", "meta"} <= set(Post.__table__.c.keys())


async def test_create_assigns_primary_key() -> None:
    db = await _setup()
    try:
        post = await Post.create(title="hello", views=3, published=True, meta={"a": 1})
        assert post.id == 1
        assert post.title == "hello"
    finally:
        await db.dispose()


async def test_find_hydrates_with_casts() -> None:
    db = await _setup()
    try:
        await Post.create(title="hi", views=1, published=True, meta={"k": "v"})
        found = await Post.find(1)
        assert found is not None
        assert found.title == "hi"
        assert found.published is True  # bool cast
        assert found.meta == {"k": "v"}  # json cast (stored as text, read back as dict)
    finally:
        await db.dispose()


async def test_dirty_tracking_and_update() -> None:
    db = await _setup()
    try:
        await Post.create(title="a", views=1, published=False, meta={})
        post = await Post.find(1)
        assert post is not None
        assert post.is_dirty() is False
        post.title = "updated"
        assert post.is_dirty() is True
        await post.save()
        again = await Post.find(1)
        assert again is not None
        assert again.title == "updated"
    finally:
        await db.dispose()


async def test_where_query_returns_models() -> None:
    db = await _setup()
    try:
        await Post.create(title="a", views=1, published=True, meta={})
        await Post.create(title="b", views=2, published=False, meta={})
        published = await Post.where(published=True).get()
        assert len(published) == 1
        assert isinstance(published[0], Post)
        assert published[0].title == "a"
    finally:
        await db.dispose()


async def test_to_dict_hides_fields() -> None:
    db = await _setup()
    try:
        post = await Post.create(title="x", views=9, published=True, meta={})
        data = post.to_dict()
        assert data["title"] == "x"
        assert "views" not in data  # __hidden__
    finally:
        await db.dispose()


async def test_delete_removes_row() -> None:
    db = await _setup()
    try:
        await Post.create(title="a", views=1, published=True, meta={})
        post = await Post.find(1)
        assert post is not None
        await post.delete()
        assert await Post.find(1) is None
    finally:
        await db.dispose()
