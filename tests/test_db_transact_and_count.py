"""transact() retries only transient failures; relation count() is a COUNT, not a full load (H4)."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError, OperationalError

from arvel.database import ConnectionResolver, Model
from arvel.database.connections import _is_transient


class _Orig(Exception):
    def __init__(self, *, sqlstate: str | None = None, code: int | None = None) -> None:
        super().__init__(code)
        self.sqlstate = sqlstate


def test_is_transient_classifies_by_driver_code() -> None:
    assert _is_transient(OperationalError("s", {}, _Orig(sqlstate="40001")))  # serialization
    assert _is_transient(OperationalError("s", {}, _Orig(sqlstate="40P01")))  # deadlock
    assert _is_transient(OperationalError("s", {}, _Orig(code=1213)))  # mysql deadlock
    assert not _is_transient(IntegrityError("s", {}, _Orig(sqlstate="23505")))  # unique violation
    assert not _is_transient(OperationalError("s", {}, _Orig(code=1062)))  # mysql dup entry
    assert not _is_transient(OperationalError("s", {}, None))


async def test_transact_does_not_retry_a_permanent_error() -> None:
    db = ConnectionResolver()
    calls = 0

    async def cb(_conn: object) -> None:
        nonlocal calls
        calls += 1
        raise IntegrityError("insert", {}, _Orig(sqlstate="23505"))

    try:
        raised = False
        try:
            await db.transact(cb, attempts=5)
        except IntegrityError:
            raised = True
        assert raised
        assert calls == 1  # permanent error: no retry burn
    finally:
        await db.dispose()


async def test_transact_retries_a_transient_error_then_succeeds() -> None:
    db = ConnectionResolver()
    calls = 0

    async def cb(_conn: object) -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise OperationalError("txn", {}, _Orig(sqlstate="40001"))
        return "ok"

    try:
        assert await db.transact(cb, attempts=5) == "ok"
        assert calls == 3
    finally:
        await db.dispose()


class Tag(Model):
    __fields__ = {"name": str}
    __fillable__ = ["name"]


class Post(Model):
    __fields__ = {"name": str}
    __fillable__ = ["name"]

    def tags(self) -> object:
        return self.belongs_to_many(Tag)


_md = sa.MetaData()
post_tag = sa.Table(
    "post_tag", _md, sa.Column("post_id", sa.Integer), sa.Column("tag_id", sa.Integer)
)


async def test_belongs_to_many_count_matches_get_and_honors_where() -> None:
    db = ConnectionResolver()
    for model in (Post, Tag):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    await db.execute(sa.schema.CreateTable(post_tag))
    try:
        post = await Post.create(name="p")
        red = await Tag.create(name="red")
        blue = await Tag.create(name="blue")
        await post.tags().attach(red.id)
        await post.tags().attach(blue.id)

        assert await post.tags().count() == 2
        assert await post.tags().count() == len(await post.tags().get())
        # a related where() narrows the count exactly as it narrows the fetch
        narrowed = post.tags().where("name", "=", "red")
        assert await narrowed.count() == 1
    finally:
        await db.dispose()
