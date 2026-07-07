"""ORM depth (doc 07) — has_many_through + polymorphic morph_many/morph_to. Test-first."""

from __future__ import annotations

import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model, morph_map


class Country(Model):
    __fields__ = {"name": str}
    __fillable__ = ["name"]

    def posts(self) -> object:
        return self.has_many_through(Post, User)


class User(Model):
    __fields__ = {"name": str, "country_id": int}
    __fillable__ = ["name", "country_id"]


class Post(Model):
    __fields__ = {"title": str, "user_id": int}
    __fillable__ = ["title", "user_id"]


class Comment(Model):
    __fields__ = {"body": str, "commentable_type": str, "commentable_id": int}
    __fillable__ = ["body", "commentable_type", "commentable_id"]

    def commentable(self) -> object:
        return self.morph_to("commentable")


class Video(Model):
    __fields__ = {"title": str}
    __fillable__ = ["title"]

    def comments(self) -> object:
        return self.morph_many(Comment, "commentable")


morph_map({"Post": Post, "Video": Video})


async def _setup() -> ConnectionResolver:
    db = ConnectionResolver()
    for model in (Country, User, Post, Comment, Video):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    return db


async def test_has_many_through() -> None:
    db = await _setup()
    try:
        country = await Country.create(name="NZ")
        user = await User.create(name="ada", country_id=country.id)
        await Post.create(title="hello", user_id=user.id)
        await Post.create(title="world", user_id=user.id)
        posts = await country.posts().get()
        assert {p.title for p in posts} == {"hello", "world"}
    finally:
        await db.dispose()


async def test_morph_many() -> None:
    db = await _setup()
    try:
        video = await Video.create(title="clip")
        await Comment.create(body="nice", commentable_type="Video", commentable_id=video.id)
        await Comment.create(body="cool", commentable_type="Video", commentable_id=video.id)
        await Comment.create(body="other", commentable_type="Post", commentable_id=video.id)
        comments = await video.comments().get()
        assert {c.body for c in comments} == {"nice", "cool"}  # only Video-typed
    finally:
        await db.dispose()


async def test_morph_to() -> None:
    db = await _setup()
    try:
        video = await Video.create(title="clip")
        comment = await Comment.create(body="hi", commentable_type="Video", commentable_id=video.id)
        parent = await comment.commentable().get()
        assert isinstance(parent, Video)
        assert parent.title == "clip"
    finally:
        await db.dispose()
