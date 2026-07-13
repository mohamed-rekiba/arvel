"""09 DB-QUERY A5 — belongs_to_many.sync is diff-based: attach missing, detach extras (only when
`detaching`), update pivot attrs for retained ids, and — the A5 bug — NEVER drop/recreate a
retained pivot row, so its untouched extra columns survive."""

from __future__ import annotations

import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model
from arvel.database.relations import SyncResult


class Tag(Model):
    __table_name__ = "sd_tags"
    __fields__ = {"name": str}
    __fillable__ = ["name"]


class Post(Model):
    __table_name__ = "sd_posts"
    __fields__ = {"title": str}
    __fillable__ = ["title"]

    def tags(self) -> object:
        return self.belongs_to_many(
            Tag, pivot="sd_post_tag", foreign_pivot_key="post_id", related_pivot_key="tag_id"
        ).with_pivot("note")


_pivot = sa.Table(
    "sd_post_tag",
    sa.MetaData(),
    sa.Column("post_id", sa.Integer),
    sa.Column("tag_id", sa.Integer),
    sa.Column("note", sa.String),
)


async def _setup() -> ConnectionResolver:
    db = ConnectionResolver()
    for model in (Post, Tag):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    await db.execute(sa.schema.CreateTable(_pivot))
    return db


async def test_sync_attaches_detaches_and_preserves_untouched_pivot_data() -> None:
    db = await _setup()
    try:
        post = await Post.create(title="hi")
        a = await Tag.create(name="a")
        b = await Tag.create(name="b")
        c = await Tag.create(name="c")
        await post.tags().attach(a.id, note="keep-me")
        await post.tags().attach(b.id, note="going-away")

        result = await post.tags().sync([a.id, c.id])

        assert isinstance(result, SyncResult)
        assert result.attached == [c.id]
        assert result.detached == [b.id]
        assert result.updated == []

        tags = await post.tags().get()
        assert {t.name for t in tags} == {"a", "c"}
        # `a`'s pivot row was retained (not dropped/recreated) — its extra column survives untouched
        by_name = {t.name: t for t in tags}
        assert by_name["a"].pivot["note"] == "keep-me"
    finally:
        await db.dispose()


async def test_sync_updates_pivot_attrs_only_when_given_and_different() -> None:
    db = await _setup()
    try:
        post = await Post.create(title="hi")
        a = await Tag.create(name="a")
        await post.tags().attach(a.id, note="v1")

        # same value given → not reported as updated
        unchanged = await post.tags().sync({a.id: {"note": "v1"}})
        assert unchanged.updated == []

        # different value given → updated, and the new value persists
        changed = await post.tags().sync({a.id: {"note": "v2"}})
        assert changed.updated == [a.id]
        rows = await post.tags().get()
        assert rows[0].pivot["note"] == "v2"
    finally:
        await db.dispose()


async def test_sync_accepts_a_bare_id_list() -> None:
    db = await _setup()
    try:
        post = await Post.create(title="hi")
        a = await Tag.create(name="a")
        b = await Tag.create(name="b")
        result = await post.tags().sync([a.id, b.id])
        assert set(result.attached) == {a.id, b.id}
        assert {t.name for t in await post.tags().get()} == {"a", "b"}
    finally:
        await db.dispose()


async def test_sync_without_detaching_never_detaches() -> None:
    db = await _setup()
    try:
        post = await Post.create(title="hi")
        a = await Tag.create(name="a")
        b = await Tag.create(name="b")
        await post.tags().attach(a.id, note="keep")

        result = await post.tags().sync_without_detaching([b.id])
        assert result.attached == [b.id]
        assert result.detached == []
        rows = await post.tags().get()
        assert {t.name for t in rows} == {"a", "b"}
        by_name = {t.name: t for t in rows}
        assert by_name["a"].pivot["note"] == "keep"  # untouched
    finally:
        await db.dispose()


async def test_sync_with_pivot_values_sets_the_same_pivot_columns_on_every_id() -> None:
    db = await _setup()
    try:
        post = await Post.create(title="hi")
        a = await Tag.create(name="a")
        b = await Tag.create(name="b")

        result = await post.tags().sync_with_pivot_values([a.id, b.id], {"note": "bulk"})
        assert set(result.attached) == {a.id, b.id}

        rows = await post.tags().get()
        assert {r.pivot["note"] for r in rows} == {"bulk"}
    finally:
        await db.dispose()


async def test_toggle_returns_the_changes_map() -> None:
    db = await _setup()
    try:
        post = await Post.create(title="hi")
        a = await Tag.create(name="a")
        b = await Tag.create(name="b")
        await post.tags().attach(a.id)

        result = await post.tags().toggle([a.id, b.id])
        assert result == {"attached": [b.id], "detached": [a.id]}
        assert {t.name for t in await post.tags().get()} == {"b"}
    finally:
        await db.dispose()
