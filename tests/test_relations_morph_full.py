"""ORM (doc 07) — complete morph set: morph_one + morph_to_many/morphed_by_many. Test-first."""

from __future__ import annotations

import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model, morph_map


class Tag(Model):
    __fields__ = {"name": str}
    __fillable__ = ["name"]

    def posts(self) -> object:
        return self.morphed_by_many(Post, "taggable")


class Post(Model):
    __fields__ = {"title": str}
    __fillable__ = ["title"]

    def tags(self) -> object:
        return self.morph_to_many(Tag, "taggable")


class Image(Model):
    __fields__ = {"url": str, "imageable_type": str, "imageable_id": int}
    __fillable__ = ["url", "imageable_type", "imageable_id"]


class Account(Model):
    __fields__ = {"name": str}
    __fillable__ = ["name"]

    def image(self) -> object:
        return self.morph_one(Image, "imageable")


morph_map({"Post": Post, "Account": Account})

_md = sa.MetaData()
taggables = sa.Table(
    "taggables",
    _md,
    sa.Column("taggable_type", sa.String),
    sa.Column("taggable_id", sa.Integer),
    sa.Column("tag_id", sa.Integer),
)


async def _setup() -> ConnectionResolver:
    db = ConnectionResolver()
    for model in (Tag, Post, Image, Account):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    await db.execute(sa.schema.CreateTable(taggables))
    return db


async def test_morph_to_many_attach_and_get() -> None:
    db = await _setup()
    try:
        post = await Post.create(title="hello")
        php = await Tag.create(name="php")
        py = await Tag.create(name="python")
        await post.tags().attach(php.id)
        await post.tags().attach(py.id)
        assert {t.name for t in await post.tags().get()} == {"php", "python"}
    finally:
        await db.dispose()


async def test_morphed_by_many_inverse() -> None:
    db = await _setup()
    try:
        post1 = await Post.create(title="a")
        post2 = await Post.create(title="b")
        php = await Tag.create(name="php")
        await post1.tags().attach(php.id)
        await post2.tags().attach(php.id)
        assert {p.title for p in await php.posts().get()} == {"a", "b"}
    finally:
        await db.dispose()


async def test_morph_one() -> None:
    db = await _setup()
    try:
        account = await Account.create(name="ada")
        await Image.create(url="a.png", imageable_type="Account", imageable_id=account.id)
        image = await account.image().get()
        assert image is not None
        assert image.url == "a.png"
    finally:
        await db.dispose()
