"""WI-arvel-031 — Epic 007 Story 6: chaperone (inverse parent hydration)."""

from __future__ import annotations

import pytest
from arvel.database import Model
from arvel.database.exceptions import UnknownRelationError
from arvel.database.query_logging import QueryLog
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Wi031Post(Model):
    __tablename__ = "wi031_posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    title: Mapped[str] = mapped_column(String(80))
    comments: Mapped[list[Wi031Comment]] = relationship(
        "Wi031Comment", back_populates="post", init=False, default_factory=list
    )


class Wi031Comment(Model):
    __tablename__ = "wi031_comments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    body: Mapped[str] = mapped_column(String(80))
    post_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("wi031_posts.id"), default=None)
    post: Mapped[Wi031Post | None] = relationship(
        "Wi031Post", back_populates="comments", init=False
    )


# A pair with no back_populates — exercises inverse inference.
class Wi031Hub(Model):
    __tablename__ = "wi031_hubs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    name: Mapped[str] = mapped_column(String(80))
    items: Mapped[list[Wi031Item]] = relationship(
        "Wi031Item", viewonly=True, init=False, default_factory=list
    )


class Wi031Item(Model):
    __tablename__ = "wi031_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    label: Mapped[str] = mapped_column(String(80))
    hub_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("wi031_hubs.id"), default=None)
    hub: Mapped[Wi031Hub | None] = relationship("Wi031Hub", init=False)


# Child has no relationship back to the parent — inference has nothing to find.
class Wi031Orphanage(Model):
    __tablename__ = "wi031_orphanages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    name: Mapped[str] = mapped_column(String(80))
    kids: Mapped[list[Wi031Kid]] = relationship(
        "Wi031Kid", viewonly=True, init=False, default_factory=list
    )


class Wi031Kid(Model):
    __tablename__ = "wi031_kids"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    name: Mapped[str] = mapped_column(String(80))
    orphanage_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("wi031_orphanages.id"), default=None
    )


async def _setup(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


class TestChaperone:
    async def test_inverse_is_loaded_parent_with_no_extra_query(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        post = await Wi031Post.create(title="hello")
        for i in range(3):
            await Wi031Comment.create(body=f"c{i}", post_id=post.id)

        session.expire_all()
        posts = await Wi031Post.with_({"comments": lambda q: q.chaperone()}).all()

        with QueryLog.capture() as log:
            for p in posts:
                for c in p.comments:
                    assert c.post is p
        assert len(log.queries) == 0

    async def test_chaperone_composes_with_a_filter(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        post = await Wi031Post.create(title="mix")
        await Wi031Comment.create(body="keep", post_id=post.id)
        await Wi031Comment.create(body="drop", post_id=post.id)

        session.expire_all()
        posts = await Wi031Post.with_(
            {"comments": lambda q: q.where(Wi031Comment.body == "keep").chaperone()}
        ).all()

        loaded = posts[0]
        assert len(loaded.comments) == 1
        assert loaded.comments[0].post is loaded

    async def test_explicit_inverse_name(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        post = await Wi031Post.create(title="explicit")
        await Wi031Comment.create(body="x", post_id=post.id)

        session.expire_all()
        posts = await Wi031Post.with_({"comments": lambda q: q.chaperone("post")}).all()
        assert posts[0].comments[0].post is posts[0]

    async def test_inverse_inferred_without_back_populates(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        hub = await Wi031Hub.create(name="h")
        for i in range(2):
            await Wi031Item.create(label=f"i{i}", hub_id=hub.id)

        session.expire_all()
        hubs = await Wi031Hub.with_({"items": lambda q: q.chaperone()}).all()

        with QueryLog.capture() as log:
            for it in hubs[0].items:
                assert it.hub is hubs[0]
        assert len(log.queries) == 0

    async def test_explicit_inverse_short_circuits_inference(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        # An explicit name works even on a model without back_populates.
        await _setup(engine)
        hub = await Wi031Hub.create(name="named")
        await Wi031Item.create(label="only", hub_id=hub.id)

        session.expire_all()
        hubs = await Wi031Hub.with_({"items": lambda q: q.chaperone("hub")}).all()
        assert hubs[0].items[0].hub is hubs[0]


class TestInverseInferenceErrors:
    async def test_uninferable_inverse_raises(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        # Kids point back to nothing → chaperone() can't infer the inverse relation.
        await _setup(engine)
        with pytest.raises(UnknownRelationError):
            Wi031Orphanage.with_({"kids": lambda q: q.chaperone()})
