"""ORM depth (doc 07) — nested eager loading with_("posts.comments"). Test-first."""

from __future__ import annotations

import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model


class Comment(Model):
    __fields__ = {"body": str, "post_id": int}
    __fillable__ = ["body", "post_id"]


class Post(Model):
    __fields__ = {"title": str, "user_id": int}
    __fillable__ = ["title", "user_id"]

    def comments(self) -> object:
        return self.has_many(Comment)


class User(Model):
    __fields__ = {"name": str}
    __fillable__ = ["name"]

    def posts(self) -> object:
        return self.has_many(Post)


async def _setup() -> ConnectionResolver:
    db = ConnectionResolver()
    for model in (User, Post, Comment):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    return db


async def test_nested_eager_load_no_n_plus_1() -> None:
    db = await _setup()
    try:
        user = await User.create(name="ada")
        post = await Post.create(title="hello", user_id=user.id)
        await Comment.create(body="nice", post_id=post.id)
        await Comment.create(body="cool", post_id=post.id)

        users = await User.with_("posts.comments").get()
        loaded_posts = users[0].relation("posts")
        assert len(loaded_posts) == 1
        loaded_comments = loaded_posts[0].relation("comments")
        assert {c.body for c in loaded_comments} == {"nice", "cool"}
    finally:
        await db.dispose()
