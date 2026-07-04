"""ORM depth (doc 07) — nested eager loading with_("posts.comments"). Test-first."""

from __future__ import annotations

import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model


class Comment(Model):
    __fields__ = {"body": str, "post_id": int}
    __fillable__ = ["body", "post_id"]

    def post(self) -> object:
        return self.belongs_to(Post)


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


async def test_to_dict_includes_loaded_relations() -> None:
    """An eager-loaded relation appears nested in to_dict(); an unloaded relation is not included."""
    db = await _setup()
    try:
        user = await User.create(name="ada")
        post = await Post.create(title="hello", user_id=user.id)
        await Comment.create(body="nice", post_id=post.id)
        await Comment.create(body="cool", post_id=post.id)

        # has-many nested in a has-many
        users = await User.with_("posts.comments").get()
        data = users[0].to_dict()
        assert data["name"] == "ada"
        assert isinstance(data["posts"], list) and len(data["posts"]) == 1
        assert {c["body"] for c in data["posts"][0]["comments"]} == {"nice", "cool"}

        # belongs-to serializes to a single nested dict
        comment = await Comment.with_("post").where("body", "nice").first()
        cdata = comment.to_dict()
        assert cdata["post"]["title"] == "hello"

        # an unloaded relation is absent (not eagerly serialized)
        bare = await User.first()
        assert "posts" not in bare.to_dict()

        # a loaded-but-empty belongs-to serializes to None (Laravel → null)
        orphan = await Comment.create(body="orphan", post_id=999)
        loaded = await Comment.with_("post").where("body", "orphan").first()
        assert loaded.to_dict()["post"] is None
        assert orphan.id is not None
    finally:
        await db.dispose()
