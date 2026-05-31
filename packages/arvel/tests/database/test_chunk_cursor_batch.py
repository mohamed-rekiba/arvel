"""chunk_by_id / lazy / cursor streaming and HasMany batch writes."""

from __future__ import annotations

from arvel.database import Model, field, id_, relationship, string
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


class CcbUser(Model):
    __tablename__ = "ccb_users"
    id: int = id_()
    name: str = string(80)
    posts: list[CcbPost] = relationship(
        "CcbPost", back_populates="author", init=False, default_factory=list
    )


class CcbPost(Model):
    __tablename__ = "ccb_posts"
    id: int = id_()
    title: str = string(120)
    user_id: int | None = field(foreign_key="ccb_users.id", default=None)
    author: CcbUser | None = relationship("CcbUser", back_populates="posts", init=False)


async def _setup(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


async def test_chunk_by_id_visits_every_row(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    for i in range(10):
        await CcbUser.create(name=f"u{i}")

    seen: list[int] = []

    async def collect(batch: list[CcbUser]) -> None:
        seen.extend(u.id for u in batch)

    await CcbUser.chunk_by_id(3, collect)

    assert len(seen) == 10
    assert seen == sorted(seen)


async def test_lazy_streams_all_rows(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    for i in range(7):
        await CcbUser.create(name=f"l{i}")

    names = [u.name async for u in CcbUser.lazy(2)]

    assert len(names) == 7


async def test_cursor_is_lazy_alias(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    for i in range(5):
        await CcbUser.create(name=f"c{i}")

    count = 0
    async for _ in CcbUser.cursor(2):
        count += 1

    assert count == 5


async def test_has_many_create_many(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    user = await CcbUser.create(name="author")

    posts = await user.has_many(CcbPost, foreign_key="user_id").create_many(
        [{"title": "a"}, {"title": "b"}, {"title": "c"}]
    )

    assert len(posts) == 3
    assert all(p.user_id == user.id for p in posts)
    assert all(p.id is not None for p in posts)


async def test_has_many_save_many(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    user = await CcbUser.create(name="author2")

    saved = await user.has_many(CcbPost, foreign_key="user_id").save_many(
        [CcbPost(title="x"), CcbPost(title="y")]
    )

    assert len(saved) == 2
    assert all(p.user_id == user.id for p in saved)
    assert all(p.id is not None for p in saved)
