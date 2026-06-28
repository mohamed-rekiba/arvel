"""C3c — relations: has_many/has_one/belongs_to, lazy + eager (no N+1)."""

from __future__ import annotations

import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model


class User(Model):
    __fields__ = {"name": str}
    __fillable__ = ["name"]

    def posts(self) -> object:
        return self.has_many(Post)

    def profile(self) -> object:
        return self.has_one(Profile)


class Post(Model):
    __fields__ = {"title": str, "user_id": int}
    __fillable__ = ["title", "user_id"]

    def author(self) -> object:
        return self.belongs_to(User)


class Profile(Model):
    __fields__ = {"bio": str, "user_id": int}
    __fillable__ = ["bio", "user_id"]


async def _setup() -> ConnectionResolver:
    db = ConnectionResolver()
    for model in (User, Post, Profile):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    u1 = await User.create(name="ada")
    u2 = await User.create(name="bob")
    await Post.create(title="p1", user_id=u1.id)
    await Post.create(title="p2", user_id=u1.id)
    await Post.create(title="p3", user_id=u2.id)
    await Profile.create(bio="hi", user_id=u1.id)
    return db


async def test_has_many_lazy() -> None:
    db = await _setup()
    try:
        user = await User.find(1)
        assert user is not None
        posts = await user.posts().get()
        assert {p.title for p in posts} == {"p1", "p2"}
    finally:
        await db.dispose()


async def test_has_one_lazy() -> None:
    db = await _setup()
    try:
        user = await User.find(1)
        assert user is not None
        profile = await user.profile().get()
        assert profile is not None
        assert profile.bio == "hi"
        user2 = await User.find(2)
        assert user2 is not None
        assert await user2.profile().get() is None
    finally:
        await db.dispose()


async def test_belongs_to_lazy() -> None:
    db = await _setup()
    try:
        post = await Post.find(1)
        assert post is not None
        author = await post.author().get()
        assert author is not None
        assert author.name == "ada"
    finally:
        await db.dispose()


async def test_eager_load_has_many() -> None:
    db = await _setup()
    try:
        users = await User.with_("posts").get()
        by_name = {u.name: u for u in users}
        assert {p.title for p in by_name["ada"].relation("posts")} == {"p1", "p2"}
        assert {p.title for p in by_name["bob"].relation("posts")} == {"p3"}
    finally:
        await db.dispose()


async def test_eager_load_belongs_to() -> None:
    db = await _setup()
    try:
        posts = await Post.with_("author").get()
        for post in posts:
            assert post.relation("author") is not None
        p1 = next(p for p in posts if p.title == "p1")
        assert p1.relation("author").name == "ada"
    finally:
        await db.dispose()
