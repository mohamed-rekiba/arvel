"""WI-arvel-035 — Epic 007 Story 10: pivot ergonomics.

with_pivot hydration, with_timestamps, order_by_pivot, where_pivot_in/_not_in/_between/_null,
the `as` accessor name, and create/save on the relation.
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from arvel.database import Model
from arvel.database.orm import BelongsToMany
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Table
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

wi035_post_tags = Table(
    "wi035_post_tags",
    Model.metadata,
    Column("post_id", Integer, ForeignKey("wi035_posts.id"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("wi035_tags.id"), primary_key=True),
    Column("role", String(40), nullable=True),
    Column("priority", Integer, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=True),
)


class Wi035Tag(Model):
    __tablename__ = "wi035_tags"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    name: Mapped[str] = mapped_column(String(80))


class Wi035Post(Model):
    __tablename__ = "wi035_posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    title: Mapped[str] = mapped_column(String(120))

    tags: ClassVar[BelongsToMany[Wi035Tag]] = (
        BelongsToMany(
            Wi035Tag,
            table=wi035_post_tags,
            foreign_key="post_id",
            related_foreign_key="tag_id",
        )
        .with_pivot("role", "priority")
        .with_timestamps()
        .as_("membership")
    )


async def _setup(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


class TestWithPivot:
    async def test_pivot_columns_hydrated(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        post = await Wi035Post.create(title="p")
        tag = await Wi035Tag.create(name="python")
        await post.tags.attach(tag.id, role="primary", priority=1)

        rows = await post.tags.all()
        assert len(rows) == 1
        assert rows[0].membership.role == "primary"
        assert rows[0].membership.priority == 1


class TestWithTimestamps:
    async def test_attach_sets_timestamps(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        post = await Wi035Post.create(title="p")
        tag = await Wi035Tag.create(name="t")
        await post.tags.attach(tag.id)

        pivot = await post.tags.pivot(tag.id)
        assert pivot is not None
        assert isinstance(pivot["created_at"], datetime)
        assert isinstance(pivot["updated_at"], datetime)


class TestOrderByPivot:
    async def test_orders_by_pivot_column(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        post = await Wi035Post.create(title="p")
        a = await Wi035Tag.create(name="a")
        b = await Wi035Tag.create(name="b")
        c = await Wi035Tag.create(name="c")
        await post.tags.attach(a.id, priority=3)
        await post.tags.attach(b.id, priority=1)
        await post.tags.attach(c.id, priority=2)

        asc = await post.tags.order_by_pivot("priority")
        assert [t.name for t in asc] == ["b", "c", "a"]
        desc = await post.tags.order_by_pivot("priority", "desc")
        assert [t.name for t in desc] == ["a", "c", "b"]


class TestWherePivotFilters:
    async def test_filters(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        post = await Wi035Post.create(title="p")
        admin = await Wi035Tag.create(name="admin")
        editor = await Wi035Tag.create(name="editor")
        viewer = await Wi035Tag.create(name="viewer")
        unset = await Wi035Tag.create(name="unset")
        await post.tags.attach(admin.id, role="admin", priority=10)
        await post.tags.attach(editor.id, role="editor", priority=5)
        await post.tags.attach(viewer.id, role="viewer", priority=1)
        await post.tags.attach(unset.id)

        in_rows = await post.tags.where_pivot_in("role", ["admin", "editor"])
        assert {t.name for t in in_rows} == {"admin", "editor"}

        not_in = await post.tags.where_pivot_not_in("role", ["admin", "editor"])
        assert {t.name for t in not_in} == {"viewer"}

        between = await post.tags.where_pivot_between("priority", 1, 5)
        assert {t.name for t in between} == {"editor", "viewer"}

        nulls = await post.tags.where_pivot_null("role")
        assert {t.name for t in nulls} == {"unset"}

        not_null = await post.tags.where_pivot_null("role", negate=True)
        assert {t.name for t in not_null} == {"admin", "editor", "viewer"}


class TestCreateAndSave:
    async def test_create_attaches_new_model(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        post = await Wi035Post.create(title="p")
        tag = await post.tags.create(pivot={"role": "owner"}, name="created")

        assert tag.id is not None
        rows = await post.tags.all()
        assert [t.name for t in rows] == ["created"]
        assert rows[0].membership.role == "owner"

    async def test_save_attaches_existing_model(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        post = await Wi035Post.create(title="p")
        tag = await Wi035Tag.create(name="saved")
        returned = await post.tags.save(tag, pivot={"priority": 7})

        assert returned is tag
        rows = await post.tags.all()
        assert [t.name for t in rows] == ["saved"]
        assert rows[0].membership.priority == 7
