"""Model.load_missing must detect async descriptor relations via the eager cache.

BelongsToMany / MorphToMany / MorphOne / MorphMany never appear in SQLAlchemy's
`unloaded` set, so an instance-level load_missing that only inspects `unloaded`
silently no-ops on exactly the relations the e-commerce kit leans on for RBAC
(User.roles / User.permissions are MorphToMany).
"""

from __future__ import annotations

from typing import Any, ClassVar

from arvel.database import Model, id_, string
from arvel.database.orm import BelongsToMany
from sqlalchemy import Column, ForeignKey, Integer, Table, event
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

lm_post_tags = Table(
    "lm_post_tags",
    Model.metadata,
    Column("post_id", Integer, ForeignKey("lm_posts.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("lm_tags.id", ondelete="CASCADE"), primary_key=True),
)


class LmTag(Model):
    __tablename__ = "lm_tags"
    id: int = id_()
    name: str = string(80)


class LmPost(Model):
    __tablename__ = "lm_posts"
    id: int = id_()
    title: str = string(200)
    tags: ClassVar[BelongsToMany[LmTag]] = BelongsToMany(
        LmTag, table=lm_post_tags, foreign_key="post_id", related_foreign_key="tag_id"
    )


class _SelectCounter:
    def __init__(self) -> None:
        self.count = 0

    def __call__(self, _conn: Connection, _cursor: Any, statement: str, *_rest: Any) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            self.count += 1


async def _setup(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


async def test_load_missing_populates_async_relation_cache(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    await _setup(engine)
    tag = await LmTag.create(name="python")
    post = await LmPost.create(title="hello")
    await post.tags.attach(tag.id)

    fresh = await LmPost.find(post.id)
    assert fresh is not None

    await fresh.load_missing("tags")

    counter = _SelectCounter()
    event.listen(engine.sync_engine, "before_cursor_execute", counter)
    try:
        loaded = await fresh.tags.all()
        # load_missing populated the eager cache, so all() serves from it — no query.
        assert counter.count == 0
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", counter)

    assert [t.id for t in loaded] == [tag.id]
