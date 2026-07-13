"""with_trashed()/only_trashed() must be full-fidelity model queries: local
scopes, relation constraints, aggregates, and OTHER global scopes still apply."""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model, SoftDeletes, scope


class CommentT(Model):
    __fields__ = {"body": str, "postt_id": int}
    __fillable__ = ["body", "postt_id"]


class PostT(Model, SoftDeletes):
    __fields__ = {"title": str, "published": bool}
    __fillable__ = ["title", "published"]

    def comments(self) -> object:
        return self.has_many(CommentT, foreign_key="postt_id")

    @scope
    def published_only(self, query: object) -> None:
        query.where("published", "=", True)  # type: ignore[attr-defined]


class PlainT(Model):
    __fields__ = {"name": str}
    __fillable__ = ["name"]


async def _setup() -> ConnectionResolver:
    db = ConnectionResolver()
    for model in (PostT, CommentT, PlainT):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    p1 = await PostT.create(title="live", published=True)
    p2 = await PostT.create(title="gone", published=True)
    await PostT.create(title="draft-gone", published=False)
    await CommentT.create(body="c1", postt_id=p1.id)
    await CommentT.create(body="c2", postt_id=p2.id)
    await (await PostT.find(p2.id)).delete()  # soft
    await (await PostT.find(3)).delete()  # soft
    return db


async def test_with_trashed_supports_local_scopes() -> None:
    db = await _setup()
    try:
        titles = sorted(p.title for p in await PostT.with_trashed().published_only().get())
        assert titles == ["gone", "live"]  # trashed included, scope applied
    finally:
        await db.dispose()


async def test_with_trashed_supports_where_has_and_with_count() -> None:
    db = await _setup()
    try:
        with_comments = await PostT.with_trashed().where_has("comments").get()
        assert sorted(p.title for p in with_comments) == ["gone", "live"]
        counted = await PostT.with_trashed().with_count("comments").order_by("id").get()
        assert [p.comments_count for p in counted] == [1, 1, 0]
    finally:
        await db.dispose()


async def test_only_trashed_returns_only_soft_deleted() -> None:
    db = await _setup()
    try:
        titles = sorted(p.title for p in await PostT.only_trashed().get())
        assert titles == ["draft-gone", "gone"]
    finally:
        await db.dispose()


async def test_trashed_queries_keep_other_global_scopes() -> None:
    db = await _setup()
    try:
        PostT.add_global_scope("published_global", lambda q: q.where("published", "=", True))
        try:
            titles = sorted(p.title for p in await PostT.with_trashed().get())
            assert titles == ["gone", "live"]  # draft-gone excluded by the OTHER global scope
            only = sorted(p.title for p in await PostT.only_trashed().get())
            assert only == ["gone"]
        finally:
            PostT.__global_scopes__.pop("published_global", None)
    finally:
        await db.dispose()


async def test_only_trashed_on_non_soft_delete_model_raises() -> None:
    db = ConnectionResolver()
    PlainT.set_connection(db)
    try:
        with pytest.raises(TypeError, match="SoftDeletes"):
            PlainT.only_trashed()
    finally:
        await db.dispose()
