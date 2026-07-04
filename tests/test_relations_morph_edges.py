"""ORM depth (doc 07) — morph relationship edge cases: empty relation, type collision, null
morph_to, and single-query (N+1 absence)."""

from __future__ import annotations

from typing import ClassVar

import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model


class MePost(Model):
    __fields__: ClassVar = {"title": str}
    __fillable__: ClassVar = ["title"]


class MeVideo(Model):
    __fields__: ClassVar = {"title": str}
    __fillable__: ClassVar = ["title"]

    def comments(self) -> object:
        return self.morph_many(MeComment, "commentable")


class MeComment(Model):
    __fields__: ClassVar = {"body": str, "commentable_type": str, "commentable_id": int}
    __fillable__: ClassVar = ["body", "commentable_type", "commentable_id"]

    def commentable(self) -> object:
        return self.morph_to("commentable")


async def _setup() -> ConnectionResolver:
    db = ConnectionResolver()
    for model in (MePost, MeVideo, MeComment):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    return db


async def test_empty_morph_relation_returns_empty_list() -> None:
    db = await _setup()
    try:
        video = await MeVideo.create(title="silent")
        assert await video.comments().get() == []  # no children → [], not None/error
    finally:
        await db.dispose()


async def test_polymorphic_type_collision_resolves_correct_parent() -> None:
    # Post#1 and Video#1 share the same primary key; morph_to must disambiguate by *_type, not *_id
    db = await _setup()
    try:
        post = await MePost.create(title="P")
        video = await MeVideo.create(title="V")
        assert post.id == video.id == 1  # same id, different models

        on_post = await MeComment.create(
            body="a", commentable_type="MePost", commentable_id=post.id
        )
        on_video = await MeComment.create(
            body="b", commentable_type="MeVideo", commentable_id=video.id
        )

        parent_a = await on_post.commentable().get()
        parent_b = await on_video.commentable().get()
        assert isinstance(parent_a, MePost) and parent_a.title == "P"
        assert isinstance(parent_b, MeVideo) and parent_b.title == "V"  # not mixed up
    finally:
        await db.dispose()


async def test_morph_to_with_null_target_returns_none() -> None:
    db = await _setup()
    try:
        orphan = await MeComment.create(body="x", commentable_type=None, commentable_id=None)
        assert await orphan.commentable().get() is None
    finally:
        await db.dispose()


async def test_morph_many_is_a_single_query_no_n_plus_1() -> None:
    db = await _setup()
    try:
        video = await MeVideo.create(title="clip")
        for body in ("one", "two", "three"):
            await MeComment.create(body=body, commentable_type="MeVideo", commentable_id=video.id)

        db.enable_query_log()
        comments = await video.comments().get()
        log = db.get_query_log()
        assert {c.body for c in comments} == {"one", "two", "three"}
        assert len(log) == 1  # one batched SELECT, not one-per-child
    finally:
        await db.dispose()
