"""ORM gap-audit completion — D1 (has_one_through), D2 (with_where_has). Test-first."""

from __future__ import annotations

import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model


# --- D1: has_one_through (Country → User → Post, single row) ---------------------
class Country(Model):
    __fields__ = {"name": str}
    __fillable__ = ["name"]

    def first_post(self) -> object:
        return self.has_one_through(Post, User)


class User(Model):
    __fields__ = {"name": str, "country_id": int}
    __fillable__ = ["name", "country_id"]

    def posts(self) -> object:
        return self.has_many(Post)


class Post(Model):
    __fields__ = {"title": str, "user_id": int, "published": bool}
    __fillable__ = ["title", "user_id", "published"]


async def _setup() -> ConnectionResolver:
    db = ConnectionResolver()
    for model in (Country, User, Post):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    return db


async def test_has_one_through_returns_single_related_row() -> None:
    db = await _setup()
    try:
        gb = await Country.create(name="GB")
        ada = await User.create(name="Ada", country_id=gb.id)
        await Post.create(title="First", user_id=ada.id, published=True)
        await Post.create(title="Second", user_id=ada.id, published=False)

        post = await gb.first_post().get()
        assert post is not None
        assert post.title == "First"  # the single (first) row, not a list
    finally:
        await db.dispose()


async def test_has_one_through_returns_none_when_absent() -> None:
    db = await _setup()
    try:
        empty = await Country.create(name="Nowhere")
        assert await empty.first_post().get() is None
    finally:
        await db.dispose()


# --- D2: with_where_has (one constraint → both filters parents AND eager load) ---
async def test_with_where_has_filters_parents_and_constrains_eager_load() -> None:
    db = await _setup()
    try:
        gb = await Country.create(name="GB")
        ada = await User.create(name="Ada", country_id=gb.id)
        await User.create(name="Silent", country_id=gb.id)  # no published posts
        await Post.create(title="Pub", user_id=ada.id, published=True)
        await Post.create(title="Draft", user_id=ada.id, published=False)

        users = await User.with_where_has("posts", lambda q: q.where(published=True)).get()

        # parent filter: only users WITH a published post
        assert {u.name for u in users} == {"Ada"}
        # eager-load constraint: the loaded posts contain ONLY published rows (same constraint)
        ada_loaded = next(u for u in users if u.name == "Ada")
        titles = {p.title for p in ada_loaded._relations["posts"]}
        assert titles == {"Pub"}  # "Draft" excluded by the same constraint
    finally:
        await db.dispose()
