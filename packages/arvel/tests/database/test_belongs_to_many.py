"""S-005-10 — BelongsToMany relation.

AC covered:
  AC-005-016-01  attach() inserts a pivot row and returns True
  AC-005-016-02  attach() on existing row upserts (returns False) without raising
  AC-005-016-03  detach() removes the pivot row
  AC-005-016-04  sync() replaces all pivot rows
  AC-005-016-05  iterating the accessor yields related model instances
  AC-005-016-06  pivot() returns dict of pivot column values for a related row
  AC-005-017-01  toggle() attaches if absent, detaches if present
"""

from __future__ import annotations

from typing import Any, ClassVar

from arvel.database import Model, Timestamps

# RED: arvel.database.orm.BelongsToMany does not exist yet
from arvel.database.orm import BelongsToMany
from sqlalchemy import Column, ForeignKey, Integer, String, Table
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

# ─── Schema ──────────────────────────────────────────────────────────────────

post_tag_table = Table(
    "btm_post_tags",
    Model.metadata,
    Column("post_id", Integer, ForeignKey("btm_posts.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("btm_tags.id", ondelete="CASCADE"), primary_key=True),
    Column("tagged_at", String(32), nullable=True),
)


class BtmTag(Model):
    __tablename__ = "btm_tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    name: Mapped[str] = mapped_column(String(80), nullable=False)


class BtmPost(Model, Timestamps):
    __tablename__ = "btm_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    title: Mapped[str] = mapped_column(String(200), nullable=False)

    tags: ClassVar[BelongsToMany[BtmTag]] = BelongsToMany(
        BtmTag,
        table=post_tag_table,
        foreign_key="post_id",
        related_foreign_key="tag_id",
    )


async def _create_tables(engine: Any) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


# ─── AC-005-016-01: attach returns True for new row ──────────────────────────


async def test_btm_attach_inserts_pivot_row(engine: Any, session: AsyncSession) -> None:
    """AC-005-016-01: attach() inserts a pivot row and returns True."""
    await _create_tables(engine)
    tag = await BtmTag.create(name="python")
    post = await BtmPost.create(title="Hello")

    inserted = await post.tags.attach(tag.id)

    assert inserted is True
    related = [t async for t in post.tags]
    assert any(t.id == tag.id for t in related)


# ─── AC-005-016-02: attach on existing row upserts without raising ────────────


async def test_btm_attach_upserts_existing_row(engine: Any, session: AsyncSession) -> None:
    """AC-005-016-02: attach() on an existing pivot row does not raise; returns False."""
    await _create_tables(engine)
    tag = await BtmTag.create(name="python")
    post = await BtmPost.create(title="Hello")

    await post.tags.attach(tag.id)
    second = await post.tags.attach(tag.id)

    assert second is False


async def test_btm_attach_with_pivot_columns(engine: Any, session: AsyncSession) -> None:
    """AC-005-016-02: attach() stores extra pivot column values."""
    await _create_tables(engine)
    tag = await BtmTag.create(name="orm")
    post = await BtmPost.create(title="ORM Post")

    await post.tags.attach(tag.id, tagged_at="2026-05-17")

    pivot_data = await post.tags.pivot(tag.id)
    assert pivot_data["tagged_at"] == "2026-05-17"


# ─── AC-005-016-03: detach removes the pivot row ─────────────────────────────


async def test_btm_detach_removes_pivot_row(engine: Any, session: AsyncSession) -> None:
    """AC-005-016-03: detach() removes the pivot row."""
    await _create_tables(engine)
    tag = await BtmTag.create(name="python")
    post = await BtmPost.create(title="Hello")
    await post.tags.attach(tag.id)

    await post.tags.detach(tag.id)

    related = [t async for t in post.tags]
    assert not any(t.id == tag.id for t in related)


async def test_btm_detach_nonexistent_is_noop(engine: Any, session: AsyncSession) -> None:
    """AC-005-016-03: detach() on a non-attached id does not raise."""
    await _create_tables(engine)
    tag = await BtmTag.create(name="python")
    post = await BtmPost.create(title="Hello")

    await post.tags.detach(tag.id)  # should not raise


# ─── AC-005-016-04: sync replaces all pivot rows ─────────────────────────────


async def test_btm_sync_replaces_pivot_rows(engine: Any, session: AsyncSession) -> None:
    """AC-005-016-04: sync() detaches stale rows and attaches new ones."""
    await _create_tables(engine)
    tag_a = await BtmTag.create(name="a")
    tag_b = await BtmTag.create(name="b")
    tag_c = await BtmTag.create(name="c")
    post = await BtmPost.create(title="Sync Post")

    await post.tags.attach(tag_a.id)
    await post.tags.attach(tag_b.id)

    await post.tags.sync([tag_b.id, tag_c.id])

    related_ids = {t.id async for t in post.tags}
    assert related_ids == {tag_b.id, tag_c.id}
    assert tag_a.id not in related_ids


async def test_btm_sync_with_empty_list_detaches_all(engine: Any, session: AsyncSession) -> None:
    """AC-005-016-04: sync([]) detaches all related rows."""
    await _create_tables(engine)
    tag = await BtmTag.create(name="python")
    post = await BtmPost.create(title="Hello")
    await post.tags.attach(tag.id)

    await post.tags.sync([])

    related = [t async for t in post.tags]
    assert related == []


# ─── AC-005-016-05: iteration yields related model instances ──────────────────


async def test_btm_iteration_yields_related_models(engine: Any, session: AsyncSession) -> None:
    """AC-005-016-05: iterating the accessor yields instances of the related model."""
    await _create_tables(engine)
    tag1 = await BtmTag.create(name="django")
    tag2 = await BtmTag.create(name="flask")
    post = await BtmPost.create(title="Frameworks")

    await post.tags.attach(tag1.id)
    await post.tags.attach(tag2.id)

    related = [t async for t in post.tags]
    assert len(related) == 2
    assert all(isinstance(t, BtmTag) for t in related)
    assert {t.name for t in related} == {"django", "flask"}


# ─── AC-005-016-06: pivot() returns dict of pivot column values ───────────────


async def test_btm_pivot_returns_pivot_columns(engine: Any, session: AsyncSession) -> None:
    """AC-005-016-06: pivot() returns a dict containing pivot column values."""
    await _create_tables(engine)
    tag = await BtmTag.create(name="fastapi")
    post = await BtmPost.create(title="FastAPI Post")
    await post.tags.attach(tag.id, tagged_at="2026-01-01")

    pivot_data = await post.tags.pivot(tag.id)

    assert isinstance(pivot_data, dict)
    assert "tagged_at" in pivot_data
    assert pivot_data["tagged_at"] == "2026-01-01"


async def test_btm_pivot_returns_none_for_unattached(engine: Any, session: AsyncSession) -> None:
    """AC-005-016-06: pivot() returns None when the row is not attached."""
    await _create_tables(engine)
    tag = await BtmTag.create(name="starlette")
    post = await BtmPost.create(title="Starlette Post")

    pivot_data = await post.tags.pivot(tag.id)

    assert pivot_data is None


# ─── AC-005-017-01: toggle ───────────────────────────────────────────────────


async def test_btm_toggle_attaches_when_absent(engine: Any, session: AsyncSession) -> None:
    """AC-005-017-01: toggle() attaches the row when it is not yet attached."""
    await _create_tables(engine)
    tag = await BtmTag.create(name="asyncio")
    post = await BtmPost.create(title="Async Post")

    result = await post.tags.toggle(tag.id)

    assert result == "attached"
    related = [t async for t in post.tags]
    assert any(t.id == tag.id for t in related)


async def test_btm_toggle_detaches_when_present(engine: Any, session: AsyncSession) -> None:
    """AC-005-017-01: toggle() detaches the row when it is already attached."""
    await _create_tables(engine)
    tag = await BtmTag.create(name="asyncio")
    post = await BtmPost.create(title="Async Post")
    await post.tags.attach(tag.id)

    result = await post.tags.toggle(tag.id)

    assert result == "detached"
    related = [t async for t in post.tags]
    assert not any(t.id == tag.id for t in related)
