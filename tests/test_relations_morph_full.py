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

    def photos(self) -> object:
        return self.morph_many(Image, "imageable")


class Company(Model):
    """Exists only to collide ids with ``Account`` (both start a fresh id sequence at 1) — the
    ``MorphMany`` proxy id/type-collision proof needs two different parent *types* sharing an id."""

    __fields__ = {"name": str}
    __fillable__ = ["name"]

    def photos(self) -> object:
        return self.morph_many(Image, "imageable")


morph_map({"Post": Post, "Account": Account, "Company": Company})

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
    for model in (Tag, Post, Image, Account, Company):
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


async def test_morph_to_many_proxy_where_in_and_pluck_scoped() -> None:
    """D7: MorphToMany exposes the same full-builder proxy surface as belongs_to_many, scoped by
    both the pivot id AND the morph type."""
    db = await _setup()
    try:
        post = await Post.create(title="hello")
        other = await Post.create(title="other")
        php = await Tag.create(name="php")
        python_tag = await Tag.create(name="python")
        rust = await Tag.create(name="rust")
        await post.tags().attach(php.id)
        await post.tags().attach(python_tag.id)
        await other.tags().attach(rust.id)  # a different parent's attachment

        names = await post.tags().where_in("id", [php.id, rust.id]).pluck("name")
        assert names == ["php"]  # rust belongs to `other`, excluded by the pivot scope

        lonely = await Post.create(title="lonely")
        assert await lonely.tags().where_in("id", [php.id]).get() == []
    finally:
        await db.dispose()


async def test_morphed_by_many_proxy_where_in_and_pluck_scoped() -> None:
    db = await _setup()
    try:
        post1 = await Post.create(title="a")
        post2 = await Post.create(title="b")
        other_post = await Post.create(title="c")
        php = await Tag.create(name="php")
        await post1.tags().attach(php.id)
        await post2.tags().attach(php.id)

        titles = await php.posts().where_in("id", [post1.id, other_post.id]).pluck("title")
        assert titles == ["a"]  # post2 is attached but excluded by the id filter
    finally:
        await db.dispose()


async def test_morph_many_proxy_where_in_scoped_by_id_and_type() -> None:
    """D7: MorphMany's ``query()`` override adds the ``{name}_type`` discriminator its inherited
    base ``query()`` would omit — a child of a different parent *type* sharing the same id is
    never returned, even through the where_in proxy."""
    db = await _setup()
    try:
        account = await Account.create(name="ada")
        company = await Company.create(name="acme")
        assert company.id == account.id  # the id-collision this test needs (fresh id sequences)

        a_img = await Image.create(url="a.png", imageable_type="Account", imageable_id=account.id)
        c_img = await Image.create(url="c.png", imageable_type="Company", imageable_id=company.id)

        urls = await account.photos().where_in("id", [a_img.id, c_img.id]).pluck("url")
        assert urls == ["a.png"]  # c_img shares imageable_id but not imageable_type — excluded
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
