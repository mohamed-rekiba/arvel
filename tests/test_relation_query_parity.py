"""Relations are query builders: a has-many/has-one relation proxies where/order_by/count to
its FK-constrained query, and create/save set the foreign key to the parent automatically."""

from __future__ import annotations

from typing import Any, ClassVar

import sqlalchemy as sa

from arvel import Model
from arvel.database import ConnectionResolver


class Writer(Model):
    __table_name__ = "writers"
    __fields__: ClassVar[dict[str, Any]] = {"name": str}
    __fillable__: ClassVar[list[str]] = ["name"]

    def posts(self) -> Any:
        return self.has_many(Article, "writer_id")

    def profile(self) -> Any:
        return self.has_one(Profile, "writer_id")


class Article(Model):
    __table_name__ = "articles"
    __fields__: ClassVar[dict[str, Any]] = {"title": str, "writer_id": int, "published": bool}
    __fillable__: ClassVar[list[str]] = ["title", "writer_id", "published"]


class Profile(Model):
    __table_name__ = "profiles"
    __fields__: ClassVar[dict[str, Any]] = {"bio": str, "writer_id": int}
    __fillable__: ClassVar[list[str]] = ["bio", "writer_id"]


async def _db() -> ConnectionResolver:
    db = ConnectionResolver()
    for model in (Writer, Article, Profile):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    return db


async def test_relation_create_sets_foreign_key() -> None:
    db = await _db()
    try:
        writer = await Writer.create(name="Ada")
        article = await writer.posts().create(title="Hello", published=True)
        assert article.writer_id == writer.id  # FK auto-set
        assert [a.title for a in await writer.posts().get()] == ["Hello"]
    finally:
        await db.dispose()


async def test_relation_save_sets_foreign_key() -> None:
    db = await _db()
    try:
        writer = await Writer.create(name="Cleo")
        draft = Article()
        draft.title = "Draft"
        saved = await writer.posts().save(draft)
        assert saved.writer_id == writer.id
        assert (await writer.posts().count()) == 1
    finally:
        await db.dispose()


async def test_relation_proxies_query_builder() -> None:
    db = await _db()
    try:
        writer = await Writer.create(name="Bob")
        await writer.posts().create(title="A", published=True)
        await writer.posts().create(title="B", published=False)
        other = await Writer.create(name="Eve")
        await other.posts().create(title="Z", published=True)  # different parent — excluded by FK

        # where / count proxy to the FK-constrained query (scoped to this parent)
        assert await writer.posts().where("published", "=", True).count() == 1
        assert await writer.posts().count() == 2
        # order_by proxies too
        titles = [a.title for a in await writer.posts().order_by("title", "desc").get()]
        assert titles == ["B", "A"]
        # the constraint is real: Eve's post is not visible through Bob's relation
        assert "Z" not in [a.title for a in await writer.posts().get()]
    finally:
        await db.dispose()


async def test_has_one_create_and_proxy() -> None:
    db = await _db()
    try:
        writer = await Writer.create(name="Ada")
        profile = await writer.profile().create(bio="hello")  # has-one create sets FK
        assert profile.writer_id == writer.id
        # has-one resolves to a single model (get() → first()) and proxies the query builder
        assert (await writer.profile().get()).bio == "hello"
        assert await writer.profile().where("bio", "=", "hello").first() is not None
    finally:
        await db.dispose()


# --- D7: belongs-to-many proxies the full builder exactly like has-many does above -------------
class Tagr(Model):
    __table_name__ = "tagsr"
    __fields__: ClassVar[dict[str, Any]] = {"label": str}
    __fillable__: ClassVar[list[str]] = ["label"]


class Postr(Model):
    __table_name__ = "postsr"
    __fields__: ClassVar[dict[str, Any]] = {"title": str}
    __fillable__: ClassVar[list[str]] = ["title"]

    def tags(self) -> Any:
        return self.belongs_to_many(
            Tagr, pivot="postr_tagr", foreign_pivot_key="postr_id", related_pivot_key="tagr_id"
        )


_postr_tagr = sa.Table(
    "postr_tagr", sa.MetaData(), sa.Column("postr_id", sa.Integer), sa.Column("tagr_id", sa.Integer)
)


async def _pivot_db() -> ConnectionResolver:
    db = ConnectionResolver()
    for model in (Postr, Tagr):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    await db.execute(sa.schema.CreateTable(_postr_tagr))
    return db


async def test_belongs_to_many_proxies_full_builder_like_has_many() -> None:
    """D7 symmetry: the same ``where_in(...).pluck(...)`` shape scopes a belongs-to-many proxy
    the same way ``test_relation_proxies_query_builder`` (above) already shows for a has-many
    relation — including an unattached parent yielding ``[]``, never the whole related table."""
    db = await _pivot_db()
    try:
        post = await Postr.create(title="p1")
        other = await Postr.create(title="p2")
        keep = await Tagr.create(label="keep")
        drop = await Tagr.create(label="drop")
        outside = await Tagr.create(label="outside")
        await post.tags().attach(keep.id)
        await post.tags().attach(drop.id)
        await other.tags().attach(outside.id)  # a different parent's attachment

        # where_in + pluck, scoped to `post`: outside (attached to `other`) never returned even
        # though its id is in the filter; drop is attached but excluded by the id filter.
        labels = await post.tags().where_in("id", [keep.id, outside.id]).pluck("label")
        assert labels == ["keep"]

        assert await post.tags().where_in("id", [drop.id, outside.id]).count() == 1

        lonely = await Postr.create(title="p3")
        assert await lonely.tags().where_in("id", [keep.id]).get() == []  # never attached
    finally:
        await db.dispose()
