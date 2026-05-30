"""S-005-12 — ORM smoke benchmark.

AC covered:
  AC-005-022-01  bulk insert 1 000 rows completes in ≤ 500 ms
  AC-005-022-02  eager-load 1 000 rows with BelongsToMany completes in ≤ 1 500 ms
  AC-005-022-03  pivot attach per row completes in ≤ 50 ms

Run exclusively via:
    uv run pytest packages/arvel/tests/database/benchmarks/ -m benchmark

Never included in the default pytest run (excluded via -m 'not benchmark').
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from arvel.database import Model, Timestamps
from arvel.database.orm import BelongsToMany
from arvel.database.session import set_active_session
from sqlalchemy import Column, ForeignKey, Integer, String, Table, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Mapped, mapped_column

# ─── Schema ──────────────────────────────────────────────────────────────────

bench_post_tag = Table(
    "bench_post_tags",
    Model.metadata,
    Column("post_id", Integer, ForeignKey("bench_posts.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("bench_tags.id", ondelete="CASCADE"), primary_key=True),
)


class BenchTag(Model):
    __tablename__ = "bench_tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    name: Mapped[str] = mapped_column(String(80), nullable=False)


class BenchPost(Model, Timestamps):
    __tablename__ = "bench_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    title: Mapped[str] = mapped_column(String(200), nullable=False)

    tags: BelongsToMany[BenchTag] = BelongsToMany(
        BenchTag,
        table=bench_post_tag,
        foreign_key="post_id",
        related_foreign_key="tag_id",
    )


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture(scope="module")
async def bench_engine() -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture(scope="module")
async def bench_session(bench_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    maker = async_sessionmaker(bench_engine, expire_on_commit=False)
    async with maker() as s:
        yield s


# ─── AC-005-022-01: bulk insert 1 000 rows ≤ 500 ms ─────────────────────────


@pytest.mark.benchmark(group="orm-insert")
def test_bulk_insert_1000_posts(benchmark: Any, bench_engine: AsyncEngine) -> None:
    """AC-005-022-01: inserting 1 000 rows completes in ≤ 500 ms."""
    maker = async_sessionmaker(bench_engine, expire_on_commit=False)

    def _run() -> None:
        async def _insert() -> None:
            async with maker() as s:
                posts = [BenchPost(title=f"Post {i}") for i in range(1000)]
                s.add_all(posts)
                await s.commit()

        asyncio.get_event_loop().run_until_complete(_insert())

    benchmark(_run)

    assert benchmark.stats["mean"] <= 0.500, (
        f"Bulk insert mean {benchmark.stats['mean']:.3f}s exceeds 500 ms threshold"
    )


# ─── AC-005-022-02: eager-load 1 000 rows ≤ 1 500 ms ────────────────────────


@pytest.mark.benchmark(group="orm-read")
def test_eager_load_1000_posts_with_tags(benchmark: Any, bench_engine: AsyncEngine) -> None:
    """AC-005-022-02: loading 1 000 posts and iterating BelongsToMany tags ≤ 1 500 ms."""
    maker = async_sessionmaker(bench_engine, expire_on_commit=False)

    def _run() -> None:
        async def _load() -> None:
            async with maker() as s:
                set_active_session(s)
                result = await s.execute(select(BenchPost).limit(1000))
                posts = result.scalars().all()
                for post in posts:
                    _ = [t async for t in post.tags]

        asyncio.get_event_loop().run_until_complete(_load())

    benchmark(_run)

    assert benchmark.stats["mean"] <= 1.500, (
        f"Eager-load mean {benchmark.stats['mean']:.3f}s exceeds 1 500 ms threshold"
    )


# ─── AC-005-022-03: pivot attach ≤ 50 ms per row ────────────────────────────


@pytest.mark.benchmark(group="orm-pivot")
def test_pivot_attach_per_row(benchmark: Any, bench_engine: AsyncEngine) -> None:
    """AC-005-022-03: single pivot attach completes in ≤ 50 ms."""
    maker = async_sessionmaker(bench_engine, expire_on_commit=False)

    async def _setup() -> tuple[int, int]:
        async with maker() as s:
            post = BenchPost(title="Pivot Post")
            tag = BenchTag(name="pivot-tag")
            s.add_all([post, tag])
            await s.commit()
            return post.id, tag.id

    loop = asyncio.get_event_loop()
    post_id, tag_id = loop.run_until_complete(_setup())

    def _run() -> None:
        async def _attach() -> None:
            async with maker() as s:
                set_active_session(s)
                post = await BenchPost.find(post_id)
                assert post is not None
                await post.tags.detach(tag_id)
                await post.tags.attach(tag_id)

        loop.run_until_complete(_attach())

    benchmark(_run)

    assert benchmark.stats["mean"] <= 0.050, (
        f"Pivot attach mean {benchmark.stats['mean'] * 1000:.1f}ms exceeds 50 ms threshold"
    )
